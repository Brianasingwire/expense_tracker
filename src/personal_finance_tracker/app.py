"""Streamlit UI. Run with `uv run personal-finance-tracker` or `streamlit run` on this file."""

from __future__ import annotations

import re
from datetime import date

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from personal_finance_tracker import analytics, charts
from personal_finance_tracker.db import ExpenseDB

st.set_page_config(page_title="Expense Tracker", page_icon="💸", layout="wide")


@st.cache_resource
def get_db() -> ExpenseDB:
    return ExpenseDB()


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
        msg = f"**{md_escape(a.category)}**: spent {a.spent:,.2f} of {a.limit:,.2f} ({a.ratio:.0%})"
        if a.level == "over":
            st.error(f"Over budget — {msg}", icon="🚨")
        elif a.level == "warning":
            st.warning(f"Nearing budget — {msg}", icon="⚠️")


db = get_db()
categories = db.categories()
all_expenses = db.get_expenses()
this_month = pd.Period(date.today(), freq="M").strftime("%Y-%m")
NEW_CATEGORY = "+ New category…"

st.title("💸 Expense Tracker")
st.caption("Log what you spend, sort it into categories, and see where your money goes.")

tab_add, tab_dash, tab_manage, tab_budgets = st.tabs(
    ["➕ Add expense", "📊 Dashboard", "🗂️ Manage expenses", "🎯 Budgets"]
)

# --- Add expense ------------------------------------------------------------
with tab_add:
    with st.form("add_expense", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        when = c1.date_input("Date", value=date.today())
        amount = c2.number_input("Amount", min_value=0.01, step=1.0, format="%.2f")
        category = c3.selectbox("Category", categories + [NEW_CATEGORY])
        new_category = st.text_input("New category name (if selected above)")
        description = st.text_input("Description", placeholder="e.g. Groceries at the market")
        submitted = st.form_submit_button("Add expense", type="primary")

    if submitted:
        new_category = new_category.strip()
        error = None
        if category == NEW_CATEGORY:
            # Reuse an existing category's spelling if the name only differs by case.
            existing = {c.lower(): c for c in categories}
            category = existing.get(new_category.lower(), new_category)
            if not category:
                error = "Please enter a name for the new category."
        elif new_category:
            error = f"Select “{NEW_CATEGORY}” to use a new category name, or clear that field."
        if error:
            st.error(error)
        else:
            db.add_expense(when, amount, category, description)
            # Immediate budget check for the month the expense falls in; shown after rerun.
            alerts = []
            budgets = db.get_budgets()
            if category in budgets:
                start, end = month_bounds(pd.Period(when, freq="M").strftime("%Y-%m"))
                alerts = analytics.budget_status(
                    db.get_expenses(start, end), {category: budgets[category]}
                )
            st.session_state["flash"] = (f"Added {amount:,.2f} to {md_escape(category)}.", alerts)
            st.rerun()

    if flash := st.session_state.pop("flash", None):
        message, alerts = flash
        st.success(message)
        render_alerts(alerts)

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

        m1, m2, m3 = st.columns(3)
        m1.metric(
            f"Spent in {selected}",
            f"{month_total:,.2f}",
            delta=f"{month_total - prev_total:,.2f} vs {prev}" if prev_total else None,
            delta_color="inverse",
        )
        m2.metric("Transactions", len(month_df))
        top = analytics.by_category(month_df)
        m3.metric("Top category", top.index[0] if not top.empty else "—")

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
            column_config={"amount": st.column_config.NumberColumn(format="%.2f")},
        )
        st.download_button(
            "Download CSV", analytics.csv_safe(view).to_csv(index=False), "expenses.csv", "text/csv"
        )

        st.subheader("Edit or delete")
        labels = {
            int(r.id): f"#{r.id} · {r.date.date()} · {r.category} · {r.amount:,.2f} · {r.description}"
            for r in view.itertuples()
        }
        if labels:
            expense_id = st.selectbox("Expense", list(labels), format_func=labels.get)
            row = all_expenses.set_index("id").loc[expense_id]
            with st.form(f"edit_{expense_id}"):
                c1, c2, c3 = st.columns(3)
                e_date = c1.date_input("Date", value=row["date"].date())
                e_amount = c2.number_input(
                    "Amount", min_value=0.01, value=float(row["amount"]), format="%.2f"
                )
                cat_options = categories if row["category"] in categories else categories + [row["category"]]
                e_cat = c3.selectbox("Category", cat_options, index=cat_options.index(row["category"]))
                e_desc = st.text_input("Description", value=row["description"])
                b1, b2 = st.columns([1, 6])
                save = b1.form_submit_button("Save", type="primary")
                delete = b2.form_submit_button("Delete")
            if save:
                db.update_expense(expense_id, e_date, e_amount, e_cat, e_desc)
                st.rerun()
            if delete:
                db.delete_expense(expense_id)
                st.rerun()

# --- Budgets ----------------------------------------------------------------
with tab_budgets:
    st.write(
        "Set a monthly limit per category. You'll get a warning at "
        f"{analytics.WARNING_THRESHOLD:.0%} and an alert once it's exceeded."
    )
    budgets = db.get_budgets()
    with st.form("budget"):
        c1, c2 = st.columns(2)
        b_cat = c1.selectbox("Category", categories)
        b_limit = c2.number_input(
            "Monthly limit", min_value=0.01, value=float(budgets.get(b_cat, 100.0)), format="%.2f"
        )
        if st.form_submit_button("Save budget", type="primary"):
            db.set_budget(b_cat, b_limit)
            st.rerun()

    if budgets:
        start, end = month_bounds(this_month)
        st.subheader(f"This month ({this_month})")
        for a in analytics.budget_status(db.get_expenses(start, end), budgets):
            c1, c2 = st.columns([6, 1])
            c1.progress(
                min(a.ratio, 1.0),
                text=f"{md_escape(a.category)}: {a.spent:,.2f} / {a.limit:,.2f} ({a.ratio:.0%})",
            )
            if c2.button("Remove", key=f"rm_{a.category}"):
                db.delete_budget(a.category)
                st.rerun()
