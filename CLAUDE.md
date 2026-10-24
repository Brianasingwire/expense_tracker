# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Expense tracker (Python 3.12+, uv, `src/` layout) built to the spec in `expense_tracker.jpg`: add expense → save to SQLite → group by category → monthly charts → budget alerts. The required stack is Python, SQLite, Pandas, Matplotlib and Streamlit, so don't swap in alternatives (e.g. Plotly, an ORM).

## Commands

```bash
uv sync                                   # install deps (incl. dev: pytest)
uv run personal-finance-tracker           # launch the Streamlit app
uv run pytest                             # all tests
uv run pytest tests/test_tracker.py::test_budget_alerts   # single test
uv add <pkg>                              # add a dependency, then regenerate requirements.txt:
uv export --no-dev --no-hashes --no-emit-project -o requirements.txt
```

No linter or formatter is configured. Run `uvx pip-audit -r requirements.txt` after dependency changes. Python is pinned at >=3.12 because Pillow 13 (which fixes CVEs) needs it.

## Architecture

The code is split into layers, and each layer only talks to the one below it:

- `db.py`: `ExpenseDB` owns all SQL. Each method opens and closes its own connection through `_connect()`, which commits on exit. Reads come back as pandas DataFrames, with `date` converted to datetime64. Dates are stored as ISO `TEXT`. Budgets are upserted, one row per category. `categories()` returns `DEFAULT_CATEGORIES` plus any custom categories that have been used.
- `analytics.py`: pure pandas functions over the DataFrame from `get_expenses()`, with no DB access. Months are keyed as `'YYYY-MM'` strings. Every function must handle an empty DataFrame. `BudgetAlert.level` (`ok` / `warning` at `WARNING_THRESHOLD` / `over`) drives the alert UI.
- `charts.py`: returns Matplotlib `Figure`s and forces the headless `Agg` backend. Callers must `plt.close(fig)` after rendering (`app.show_fig` does this).
- `app.py`: the Streamlit script, re-executed top to bottom on every interaction. It uses absolute imports (`from personal_finance_tracker import ...`) because Streamlit runs it as a script, not as a module. The DB is a `st.cache_resource` singleton. After any write, call `st.rerun()` so the data loaded at the top of the script is refreshed. Messages that need to survive the rerun go through `st.session_state["flash"]`, which is rendered above the tabs. Widgets whose label or options change between reruns need a fixed `key=`, or their value resets.
- `__init__.py:main()`: the `personal-finance-tracker` entry point, which wraps `streamlit run app.py`.

The DB file comes from the `EXPENSE_DB_PATH` environment variable, read when `ExpenseDB()` is constructed and defaulting to `./expenses.db` (gitignored). `tests/test_tracker.py` covers the DB and analytics with `tmp_path` DBs. `tests/test_app.py` drives the UI headlessly through `streamlit.testing.v1.AppTest`; its fixture sets `EXPENSE_DB_PATH` and calls `st.cache_resource.clear()`.

## Security conventions

- The server binds to `127.0.0.1`, because the app has no auth. `main()` passes the flag and `.streamlit/config.toml` covers a plain `streamlit run`.
- User text shown through Markdown-rendering calls (`st.success`, `st.error`, `st.warning`, `st.progress` text, `st.metric` value) must go through `app.md_escape`.
- CSV exports go through `analytics.csv_safe`, which neutralises spreadsheet formulas.
- `.str.contains` on user input uses `regex=False`.
- `charts.py` disables mathtext (`text.parse_math`), so a `$` in a category name can't crash rendering.
- Data files, exports and secrets are gitignored.
