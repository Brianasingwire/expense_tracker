"""SQLite persistence layer: CRUD for expenses and monthly category budgets."""

from __future__ import annotations

import math
import os
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterator

import pandas as pd

DEFAULT_DB_PATH = Path("expenses.db")  # overridden by the EXPENSE_DB_PATH env var

DEFAULT_CATEGORIES = [
    "Food",
    "Transport",
    "Housing",
    "Utilities",
    "Entertainment",
    "Health",
    "Shopping",
    "Other",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT    NOT NULL,           -- ISO format YYYY-MM-DD
    amount      REAL    NOT NULL CHECK (amount > 0),
    category    TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);

CREATE TABLE IF NOT EXISTS budgets (
    category      TEXT PRIMARY KEY,
    monthly_limit REAL NOT NULL CHECK (monthly_limit > 0)
);
"""


def _positive_money(value: float, name: str) -> float:
    """Round to cents, then validate (so 0.004, NaN and inf are rejected, not stored)."""
    value = round(float(value), 2)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be at least 0.01")
    return value


class ExpenseDB:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = str(path or os.environ.get("EXPENSE_DB_PATH", DEFAULT_DB_PATH))
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- Expenses (CRUD) ---------------------------------------------------

    def add_expense(
        self, when: date, amount: float, category: str, description: str = ""
    ) -> int:
        amount = _positive_money(amount, "amount")
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO expenses (date, amount, category, description) "
                "VALUES (?, ?, ?, ?)",
                (when.isoformat(), amount, category, description.strip()),
            )
            return cur.lastrowid

    def update_expense(
        self, expense_id: int, when: date, amount: float, category: str, description: str
    ) -> None:
        amount = _positive_money(amount, "amount")
        with self._connect() as conn:
            conn.execute(
                "UPDATE expenses SET date = ?, amount = ?, category = ?, description = ? "
                "WHERE id = ?",
                (when.isoformat(), amount, category, description.strip(), expense_id),
            )

    def delete_expense(self, expense_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))

    def get_expenses(self, start: date | None = None, end: date | None = None) -> pd.DataFrame:
        """Return expenses (optionally within [start, end]) as a DataFrame, newest first."""
        query = "SELECT id, date, amount, category, description FROM expenses WHERE 1=1"
        params: list[str] = []
        if start:
            query += " AND date >= ?"
            params.append(start.isoformat())
        if end:
            query += " AND date <= ?"
            params.append(end.isoformat())
        query += " ORDER BY date DESC, id DESC"
        with self._connect() as conn:
            df = pd.read_sql_query(query, conn, params=params)
        df["date"] = pd.to_datetime(df["date"])
        return df

    def categories(self) -> list[str]:
        """Default categories plus any custom ones already used."""
        with self._connect() as conn:
            used = [r[0] for r in conn.execute("SELECT DISTINCT category FROM expenses")]
            budgeted = [r[0] for r in conn.execute("SELECT category FROM budgets")]
        extra = sorted(set(used + budgeted) - set(DEFAULT_CATEGORIES))
        return DEFAULT_CATEGORIES + extra

    # --- Budgets -----------------------------------------------------------

    def set_budget(self, category: str, monthly_limit: float) -> None:
        monthly_limit = _positive_money(monthly_limit, "monthly_limit")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO budgets (category, monthly_limit) VALUES (?, ?) "
                "ON CONFLICT(category) DO UPDATE SET monthly_limit = excluded.monthly_limit",
                (category, monthly_limit),
            )

    def delete_budget(self, category: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM budgets WHERE category = ?", (category,))

    def get_budgets(self) -> dict[str, float]:
        with self._connect() as conn:
            rows = conn.execute("SELECT category, monthly_limit FROM budgets ORDER BY category")
            return {r["category"]: r["monthly_limit"] for r in rows}
