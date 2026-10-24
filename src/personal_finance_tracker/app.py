"""Streamlit UI. Run with `uv run personal-finance-tracker` (binds to localhost only)."""

from __future__ import annotations

import re
import os
from datetime import date

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from personal_finance_tracker import analytics, charts, currency
from personal_finance_tracker.db import DEFAULT_DB_PATH, ExpenseDB

st.set_page_config(page_title="Expense Tracker", layout="wide")


@st.cache_resource(max_entries=1)
def get_db(path: str, class_id: int) -> ExpenseDB:
    # Keyed on the class identity: a runOnSave reload of any package file re-imports
    # db.py, so this builds an instance of the current class. max_entries=1 drops the
    # stale instance (and its old class) instead of keeping one per save.
    return ExpenseDB(path)


def month_bounds(period: str) -> tuple[date, date]:
    p = pd.Period(period, freq="M")
    return p.start_time.date(), p.end_time.date()


def show_fig(fig) -> None:
    st.pyplot(fig, width="stretch")
    plt.close(fig)


def md_escape(text: str) -> str:
    """Escape Markdown so user text can't inject links/images into st.success/error/etc."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|<>~$:])", r"\\\1", text)


def render_alerts(alerts: list[analytics.BudgetAlert]) -> None:
    for a in alerts:
        msg = f"**{md_escape(a.category)}**: spent {currency.fmt(a.spent)} of {currency.fmt(a.limit)} ({a.ratio:.0%})"
        if a.level == "over":
            st.error(f"Over budget — {msg}")
        elif a.level == "warning":
            st.warning(f"Nearing budget — {msg}")


db = get_db(os.environ.get("EXPENSE_DB_PATH", str(DEFAULT_DB_PATH)), id(ExpenseDB))
categories = db.categories()
all_expenses = db.get_expenses()
this_month = pd.Period(date.today(), freq="M").strftime("%Y-%m")
NEW_CATEGORY = "+ New category…"
AMOUNT_ERROR = "Enter an amount greater than 0."

st.title("Expense Tracker")
st.caption("Log what you spend, sort it into categories, and see where your money goes.")

if flash := st.session_state.pop("flash", None):
    message, alerts = flash
    st.success(message)
    render_alerts(alerts)

tab_add, tab_dash, tab_manage, tab_budgets = st.tabs(
    ["Add expense", "Dashboard", "Manage expenses", "Budgets"]
)

# --- Add expense ------------------------------------------------------------
with tab_add:
    # Not clear_on_submit: a rejected submit must keep the user's input. After a
    # successful add the counter changes every key, so the browser renders fresh
    # widgets with their defaults (popping session-state keys doesn't reset the browser).
    n = st.session_state.setdefault("add_form_n", 0)
    with st.form(f"add_expense_{n}"):
        c1, c2, c3 = st.columns(3)
        when = c1.date_input("Date", value=date.today(), key=f"add_date_{n}")
        amount = c2.number_input(
            f"Amount ({currency.CODE})",
            min_value=currency.INPUT_MIN,
            step=currency.STEP,
            format=currency.INPUT_FORMAT,
            key=f"add_amount_{n}",
        )
        category = c3.selectbox("Category", categories + [NEW_CATEGORY], key=f"add_category_{n}")
        new_category = st.text_input("New category name (if selected above)", key=f"add_new_category_{n}")
        description = st.text_input(
            "Description", placeholder="e.g. Groceries at the market", key=f"add_description_{n}"
        )
        submitted = st.form_submit_button("Add expense", type="primary")

    if submitted:
        new_category = new_category.strip()
        errors = []
        if category == NEW_CATEGORY:
            # Reuse an existing category's spelling if the name only differs by case.
            existing = {c.lower(): c for c in categories}
            category = existing.get(new_category.lower(), new_category)
            if not category:
                errors.append("Please enter a name for the new category.")
        elif new_category:
            errors.append(f"Select “{NEW_CATEGORY}” to use a new category name, or clear that field.")
        if not currency.is_positive(amount):
            errors.append(AMOUNT_ERROR)
        for error in errors:
            st.error(error)
        if not errors:
            db.add_expense(when, amount, category, description)
            # Immediate budget check for the month the expense falls in; shown after rerun.
            alerts = []
            budgets = db.get_budgets()
            if category in budgets:
                start, end = month_bounds(pd.Period(when, freq="M").strftime("%Y-%m"))
                alerts = analytics.budget_status(
                    db.get_expenses(start, end), {category: budgets[category]}
                )
            st.session_state["flash"] = (f"Added {currency.fmt(amount)} to {md_escape(category)}.", alerts)
            st.session_state["add_form_n"] = n + 1
            st.rerun()

# --- Dashboard --------------------------------------------------------------
with tab_dash:
    if all_expenses.empty:
        st.info("No expenses yet — add one in the **Add expense** tab.")
    else:
        months = sorted(
            set(all_expenses["date"].dt.to_period("M").astype(str)) | {this_month},
            reverse=True,
        )
        selected = st.selectbox("Month", months, index=months.index(this_month))
        start, end = month_bounds(selected)
        month_df = db.get_expenses(start, end)

        totals = analytics.monthly_totals(all_expenses)
        prev = str(pd.Period(selected, freq="M") - 1)
        month_total = float(month_df["amount"].sum())
        prev_total = float(totals.get(prev, 0.0))
        no_change = currency.is_zero(month_total - prev_total)

        m1, m2, m3 = st.columns(3)
        m1.metric(
            f"Spent in {selected}",
            currency.fmt(month_total),
            delta=f"{currency.signed(month_total - prev_total)} vs {prev}" if prev_total else None,
            # Streamlit reads any delta without a leading "-" as an increase, so a
            # zero change gets no arrow and a neutral colour.
            delta_color="off" if no_change else "inverse",
            delta_arrow="off" if no_change else "auto",
        )
        m2.metric("Transactions", len(month_df))
        top = analytics.by_category(month_df)
        m3.metric("Top category", md_escape(top.index[0]) if not top.empty else "—")

        alerts = analytics.budget_status(month_df, db.get_budgets())
        render_alerts(alerts)

        left, right = st.columns(2)
        with left:
            if top.empty:
                st.info(f"No expenses in {selected}.")
            else:
                show_fig(charts.category_bar(top))
        with right:
            show_fig(charts.monthly_bar(totals))

        st.subheader("All months by category")
        show_fig(charts.monthly_stacked(analytics.monthly_by_category(all_expenses)))

# --- Manage (read / update / delete) ----------------------------------------
with tab_manage:
    if all_expenses.empty:
        st.info("Nothing to manage yet.")
    else:
        f1, f2 = st.columns(2)
        cat_filter = f1.multiselect("Filter by category", categories)
        text_filter = f2.text_input("Search description")
        view = all_expenses
        if cat_filter:
            view = view[view["category"].isin(cat_filter)]
        if text_filter:
            view = view[view["description"].str.contains(text_filter, case=False, na=False, regex=False)]

        st.dataframe(
            view.assign(date=view["date"].dt.date),
            hide_index=True,
            width="stretch",
            column_config={
                "amount": st.column_config.NumberColumn(
                    f"amount ({currency.CODE})",
                    format="localized",  # thousands separators
                    step=10 ** -currency.DECIMALS,  # sets displayed decimals
                )
            },
        )
        st.download_button(
            "Download CSV", analytics.csv_safe(view).to_csv(index=False), "expenses.csv", "text/csv"
        )

        st.subheader("Edit or delete")
        labels = {
            int(r.id): f"#{r.id} · {r.date.date()} · {r.category} · {currency.fmt(r.amount)} · {r.description}"
            for r in view.itertuples()
        }
        if labels:
            # Fixed key: otherwise the selection resets whenever a label changes (e.g. after Save).
            expense_id = st.selectbox(
                "Expense", list(labels), format_func=labels.get, key="edit_expense_id"
            )
            row = all_expenses.set_index("id").loc[expense_id]
            with st.form(f"edit_{expense_id}"):
                c1, c2, c3 = st.columns(3)
                e_date = c1.date_input("Date", value=row["date"].date())
                e_amount = c2.number_input(
                    f"Amount ({currency.CODE})",
                    min_value=currency.INPUT_MIN,
                    step=currency.STEP,
                    value=float(row["amount"]),
                    format=currency.INPUT_FORMAT,
                )
                cat_options = categories if row["category"] in categories else categories + [row["category"]]
                e_cat = c3.selectbox("Category", cat_options, index=cat_options.index(row["category"]))
                e_desc = st.text_input("Description", value=row["description"])
                b1, b2 = st.columns([1, 6])
                save = b1.form_submit_button("Save", type="primary")
                delete = b2.form_submit_button("Delete")
            # An unchanged amount is accepted even if it predates whole-shilling input (e.g. 0.4).
            amount_ok = currency.is_positive(e_amount) or e_amount == float(row["amount"])
            if save and not amount_ok:
                st.error(AMOUNT_ERROR)
            elif save:
                db.update_expense(expense_id, e_date, e_amount, e_cat, e_desc)
                st.session_state["flash"] = (f"Updated expense #{expense_id}.", [])
                st.rerun()
            if delete:
                db.delete_expense(expense_id)
                st.session_state["flash"] = (f"Deleted expense #{expense_id}.", [])
                st.rerun()

# --- Budgets ----------------------------------------------------------------
with tab_budgets:
    st.write(
        "Set a monthly limit per category. You'll get a warning at "
        f"{analytics.WARNING_THRESHOLD:.0%} and an alert once it's exceeded."
    )
    budgets = db.get_budgets()
    # Category is chosen outside the form so the limit field pre-fills as soon as it
    # changes; the per-category key keeps the typed value stable through submit.
    c1, c2 = st.columns(2)
    b_cat = c1.selectbox("Category", categories, key="budget_category")
    with st.form("budget"):
        b_limit = st.number_input(
            f"Monthly limit for {md_escape(b_cat)} ({currency.CODE})",
            min_value=currency.INPUT_MIN,
            step=currency.STEP,
            value=float(budgets.get(b_cat, currency.DEFAULT_BUDGET)),
            format=currency.INPUT_FORMAT,
            key=f"budget_limit_{b_cat}",
        )
        save_budget = st.form_submit_button("Save budget", type="primary")
    if save_budget and not currency.is_positive(b_limit):
        st.error(AMOUNT_ERROR)
    elif save_budget:
        db.set_budget(b_cat, b_limit)
        st.session_state["flash"] = (f"Saved budget for {md_escape(b_cat)}.", [])
        st.rerun()

    if budgets:
        start, end = month_bounds(this_month)
        st.subheader(f"This month ({this_month})")
        for a in analytics.budget_status(db.get_expenses(start, end), budgets):
            c1, c2 = st.columns([6, 1])
            c1.progress(
                min(a.ratio, 1.0),
                text=f"{md_escape(a.category)}: {currency.number(a.spent)} / {currency.fmt(a.limit)} ({a.ratio:.0%})",
            )
            if c2.button("Remove", key=f"rm_{a.category}"):
                db.delete_budget(a.category)
                st.rerun()
