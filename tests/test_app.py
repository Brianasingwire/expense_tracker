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
