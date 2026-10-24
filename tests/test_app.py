"""Headless UI tests for the Streamlit app."""

from datetime import date
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

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
    form.selectbox[0].set_value("+ New category…")
    form.text_input[0].set_value("TV subscriptions")
    form.button[0].click()
    at.run()
    form = add_tab(at)
    form.selectbox[0].set_value("+ New category…")
    form.text_input[0].set_value("tv SUBSCRIPTIONS")
    form.button[0].click()
    at.run()
    assert list(db.get_expenses()["category"]).count("TV subscriptions") == 2


def test_new_category_name_without_selecting_option_is_rejected(db):
    at = run_app()
    form = add_tab(at)
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
    assert budgets.number_input[0].value == 100.0  # default for a category with no budget
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
