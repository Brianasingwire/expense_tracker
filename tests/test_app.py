"""Headless UI tests for the Streamlit app."""

from datetime import date, timedelta
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from personal_finance_tracker import currency
from personal_finance_tracker.db import ExpenseDB

APP = str(Path(__file__).parents[1] / "src" / "personal_finance_tracker" / "app.py")


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPENSE_DB_PATH", str(tmp_path / "app.db"))
    st.cache_resource.clear()  # get_db() is cached across AppTest runs
    db = ExpenseDB()
    db.add_expense(date.today(), 95.0, "Food", "groceries (weekly)")
    return db


def run_app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception, at.exception
    return at


def add_tab(at: AppTest):
    return at.tabs[0]


def test_add_expense_triggers_budget_alert(db):
    db.set_budget("Food", 100)
    at = run_app()
    form = add_tab(at)
    form.number_input[0].set_value(10.0)
    form.button[0].click()
    at.run()
    assert not at.exception
    assert len(db.get_expenses()) == 2
    assert any("Over budget" in e.value for e in at.error)


def test_new_category_keeps_casing_and_reuses_existing(db):
    at = run_app()
    form = add_tab(at)
    form.number_input[0].set_value(5000.0)
    form.selectbox[0].set_value("+ New category…")
    form.text_input[0].set_value("TV subscriptions")
    form.button[0].click()
    at.run()
    form = add_tab(at)
    form.number_input[0].set_value(5000.0)
    form.selectbox[0].set_value("+ New category…")
    form.text_input[0].set_value("tv SUBSCRIPTIONS")
    form.button[0].click()
    at.run()
    assert list(db.get_expenses()["category"]).count("TV subscriptions") == 2


def test_new_category_name_without_selecting_option_is_rejected(db):
    at = run_app()
    form = add_tab(at)
    form.number_input[0].set_value(5000.0)
    form.text_input[0].set_value("Pets")  # Category left on the default
    form.button[0].click()
    at.run()
    assert len(db.get_expenses()) == 1
    assert any("New category" in e.value for e in at.error)


def test_search_treats_input_literally(db):
    at = run_app()
    search = next(t for t in at.text_input if t.label == "Search description")
    search.set_value("(weekly").run()
    assert not at.exception
    assert len(at.dataframe[0].value) == 1


def test_category_markdown_is_escaped(db):
    db.add_expense(date.today(), 200.0, "![x](http://evil/p.png)")
    db.set_budget("![x](http://evil/p.png)", 100)
    at = run_app()
    rendered = " ".join(e.value for e in at.error)
    assert "Over budget" in rendered
    assert "![x](http" not in rendered


def test_budget_saved_for_selected_category(db):
    at = run_app()
    budgets = at.tabs[3]
    budgets.number_input[0].set_value(80.0)
    budgets.button[0].click()
    at.run()
    at.selectbox(key="budget_category").set_value("Transport").run()
    budgets = at.tabs[3]
    assert budgets.number_input[0].value == currency.DEFAULT_BUDGET  # no budget saved yet
    budgets.number_input[0].set_value(50.0)
    budgets.button[0].click()
    at.run()
    assert not at.exception
    assert db.get_budgets() == {"Food": 80.0, "Transport": 50.0}
    # Switching back pre-fills the saved limit.
    at.selectbox(key="budget_category").set_value("Food").run()
    assert at.tabs[3].number_input[0].value == 80.0


def test_remove_budget(db):
    db.set_budget("Food", 100)
    at = run_app()
    at.button(key="rm_Food").click()
    at.run()
    assert db.get_budgets() == {}


def test_edit_keeps_selection_and_delete_hits_right_row(db):
    second = db.add_expense(date.today(), 5.0, "Transport", "bus")
    first = int(db.get_expenses()["id"].min())
    at = run_app()
    at.selectbox(key="edit_expense_id").set_value(first).run()
    manage = at.tabs[2]
    desc = next(t for t in manage.text_input if t.label == "Description")
    desc.set_value("groceries edited")
    next(b for b in manage.button if b.label == "Save").click()
    at.run()
    assert not at.exception
    assert at.selectbox(key="edit_expense_id").value == first
    next(b for b in at.tabs[2].button if b.label == "Delete").click()
    at.run()
    assert list(db.get_expenses()["id"]) == [second]


def test_top_category_metric_is_escaped(db):
    db.add_expense(date.today(), 500.0, "[pay](http://evil)")
    at = run_app()
    top = next(m for m in at.metric if m.label == "Top category")
    assert "[pay](http" not in top.value


def test_amounts_shown_in_ugx(db):
    db.set_budget("Food", 50)
    at = run_app()
    spent = next(m for m in at.metric if m.label.startswith("Spent in"))
    assert spent.value == "UGX 95"
    assert any("UGX 95 of UGX 50" in e.value for e in at.error)
    assert at.tabs[0].number_input[0].label == "Amount (UGX)"


def test_small_stored_amounts_do_not_crash(db):
    # Stored before UGX became the default (DB accepts down to 0.01).
    db.add_expense(date.today(), 0.5, "Food", "old cents entry")
    db.set_budget("Food", 0.5)
    at = run_app()
    assert not at.exception
    assert len(at.tabs[3].number_input) == 1  # Budgets tab rendered


def test_spending_drop_shows_down_arrow(db):
    from streamlit.proto.Metric_pb2 import Metric as MetricProto

    last_month = (date.today().replace(day=1) - timedelta(days=1))
    db.add_expense(last_month, 5000.0, "Food")  # this month: 95
    at = run_app()
    spent = next(m for m in at.metric if m.label.startswith("Spent in"))
    assert spent.proto.delta.startswith("-UGX 4,905")
    assert spent.proto.direction == MetricProto.MetricDirection.DOWN


def test_amount_input_starts_at_zero(db):
    at = run_app()
    amount = add_tab(at).number_input[0]
    assert amount.value == 0.0 and amount.min == 0.0 and amount.step == 1000.0
    amount.increment().increment()  # two "+" clicks (committed on form submit)
    assert amount.value == 2000.0
    add_tab(at).button[0].click()
    at.run()
    assert 2000.0 in db.get_expenses()["amount"].values


def test_zero_amounts_are_rejected(db):
    at = run_app()
    add_tab(at).button[0].click()  # amount left at 0
    at.run()
    assert any("greater than 0" in e.value for e in at.error)
    assert len(db.get_expenses()) == 1

    at.tabs[3].number_input[0].set_value(0.0)
    at.tabs[3].button[0].click()
    at.run()
    assert any("greater than 0" in e.value for e in at.error)
    assert db.get_budgets() == {}


def test_add_round_amount(db):
    at = run_app()
    add_tab(at).number_input[0].set_value(7000.0)
    add_tab(at).button[0].click()
    at.run()
    assert at.success[0].value == "Added UGX 7,000 to Food."


def test_rejected_add_keeps_input_and_success_resets(db):
    at = run_app()
    form = add_tab(at)
    form.selectbox[0].set_value("Transport")
    next(t for t in form.text_input if t.label == "Description").set_value("Lunch with client")
    form.button[0].click()  # amount left at 0
    at.run()
    assert any("greater than 0" in e.value for e in at.error)

    form = add_tab(at)
    assert form.selectbox[0].value == "Transport"
    assert next(t for t in form.text_input if t.label == "Description").value == "Lunch with client"
    form.number_input[0].set_value(5000.0)
    form.button[0].click()
    at.run()
    row = db.get_expenses().iloc[0]
    assert (row["amount"], row["category"], row["description"]) == (5000.0, "Transport", "Lunch with client")

    # After a successful add the form is rebuilt under new keys. Popping the old keys
    # isn't enough: the browser keeps showing (and resubmits) the old values.
    assert at.session_state["add_form_n"] == 1
    assert at.number_input(key="add_amount_1").value == 0.0
    assert at.date_input(key="add_date_1").value == date.today()
    assert at.selectbox(key="add_category_1").value == "Food"
    assert at.text_input(key="add_description_1").value == ""


def test_add_shows_all_errors_at_once(db):
    at = run_app()
    add_tab(at).selectbox[0].set_value("+ New category…")  # name blank, amount 0
    add_tab(at).button[0].click()
    at.run()
    messages = [e.value for e in at.error]
    assert any("name for the new category" in m for m in messages)
    assert any("greater than 0" in m for m in messages)


def test_no_change_month_has_no_arrow(db):
    from streamlit.proto.Metric_pb2 import Metric as MetricProto

    last_month = date.today().replace(day=1) - timedelta(days=1)
    db.add_expense(last_month, 95.0, "Food")  # same as this month
    at = run_app()
    spent = next(m for m in at.metric if m.label.startswith("Spent in"))
    assert spent.proto.delta.startswith("UGX 0 vs")
    assert spent.proto.direction == MetricProto.MetricDirection.NONE


def test_edit_form_amount_validation(db):
    old = db.add_expense(date.today(), 0.4, "Food", "cents-era row")
    at = run_app()
    at.selectbox(key="edit_expense_id").set_value(old).run()
    manage = at.tabs[2]
    next(t for t in manage.text_input if t.label == "Description").set_value("renamed")
    next(b for b in manage.button if b.label == "Save").click()
    at.run()
    row = db.get_expenses().set_index("id").loc[old]
    assert (row["amount"], row["description"]) == (0.4, "renamed")  # unchanged amount accepted

    manage = at.tabs[2]
    next(n for n in manage.number_input if n.label.startswith("Amount")).set_value(0.0)
    next(b for b in manage.button if b.label == "Save").click()
    at.run()
    assert any("greater than 0" in e.value for e in at.error)
    assert db.get_expenses().set_index("id").loc[old]["amount"] == 0.4
