"""Pandas aggregations: category grouping, monthly totals and budget alerts."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Fraction of a budget at which a "warning" alert is raised.
WARNING_THRESHOLD = 0.8


def by_category(expenses: pd.DataFrame) -> pd.Series:
    """Total spent per category, largest first."""
    if expenses.empty:
        return pd.Series(dtype=float, name="amount")
    return expenses.groupby("category")["amount"].sum().sort_values(ascending=False)


def _all_months(dates: pd.Series) -> pd.Index:
    """Every 'YYYY-MM' from the first to the last date, so gaps show up as zero months."""
    periods = dates.dt.to_period("M")
    return pd.period_range(periods.min(), periods.max(), freq="M").astype(str)


def monthly_totals(expenses: pd.DataFrame) -> pd.Series:
    """Total spent per calendar month, indexed by 'YYYY-MM' in chronological order."""
    if expenses.empty:
        return pd.Series(dtype=float, name="amount")
    months = expenses["date"].dt.to_period("M").astype(str)
    totals = expenses.groupby(months)["amount"].sum()
    return totals.reindex(_all_months(expenses["date"]), fill_value=0.0)


def monthly_by_category(expenses: pd.DataFrame) -> pd.DataFrame:
    """Month x category pivot table of spending (missing combos filled with 0)."""
    if expenses.empty:
        return pd.DataFrame()
    months = expenses["date"].dt.to_period("M").astype(str).rename("month")
    pivot = expenses.groupby([months, "category"])["amount"].sum().unstack(fill_value=0.0)
    return pivot.reindex(_all_months(expenses["date"]), fill_value=0.0)


def csv_safe(df: pd.DataFrame) -> pd.DataFrame:
    """Neutralise spreadsheet formulas in text columns before CSV export."""
    def escape(value):
        if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
            return "'" + value
        return value

    out = df.copy()
    for col in ("category", "description"):
        out[col] = out[col].map(escape)
    return out


@dataclass(frozen=True)
class BudgetAlert:
    category: str
    spent: float
    limit: float

    @property
    def ratio(self) -> float:
        return self.spent / self.limit

    @property
    def level(self) -> str:
        if self.ratio >= 1:
            return "over"
        if self.ratio >= WARNING_THRESHOLD:
            return "warning"
        return "ok"


def budget_status(month_expenses: pd.DataFrame, budgets: dict[str, float]) -> list[BudgetAlert]:
    """Compare one month's spending per category against its budget, worst first."""
    spent = by_category(month_expenses)
    statuses = [
        # Round to cents so float noise (99.99999999999999) can't drop an alert level.
        BudgetAlert(category, round(float(spent.get(category, 0.0)), 2), limit)
        for category, limit in budgets.items()
    ]
    return sorted(statuses, key=lambda s: s.ratio, reverse=True)
