# Personal Finance Tracker

Log what you spend, sort it into categories, and see where your money goes with monthly totals and charts.

**Flow:** Add expense → Save to SQLite → Group by category → Monthly charts → Budget alerts

**Stack:** Python · SQLite · Pandas · Matplotlib · Streamlit

## Features
- **Add expense**: date, amount, category (built-in or custom), description
- **Dashboard**: monthly total vs. previous month, spending by category, monthly trend, and a stacked month × category chart
- **Manage**: filter, search, edit, delete, and export to CSV
- **Budgets**: monthly limit per category, with a warning at 80% and an alert once it's exceeded (also shown right after you add an expense)

## Run
```bash
uv sync
uv run personal-finance-tracker      # opens the Streamlit app
```
Data is stored in `expenses.db` in the current directory. Set `EXPENSE_DB_PATH` to use a different file.

Amounts are in Ugandan shillings (UGX) by default, shown without decimals. Set `EXPENSE_CURRENCY` (e.g. `EXPENSE_CURRENCY=USD`) to use another currency.

## Test
```bash
uv run pytest
```

## Layout
```
src/personal_finance_tracker/
  db.py         # SQLite CRUD (expenses, budgets)
  analytics.py  # Pandas grouping, monthly totals, budget alerts
  charts.py     # Matplotlib figures
  app.py        # Streamlit UI
tests/test_tracker.py
```
