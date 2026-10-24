import importlib

import pytest

from personal_finance_tracker import currency


@pytest.fixture(autouse=True)
def default_currency(monkeypatch):
    """Run every test with the default currency (UGX), whatever the shell sets."""
    monkeypatch.delenv("EXPENSE_CURRENCY", raising=False)
    importlib.reload(currency)
    yield
    monkeypatch.delenv("EXPENSE_CURRENCY", raising=False)
    importlib.reload(currency)


@pytest.fixture
def use_currency(monkeypatch):
    """Switch currency for one test, e.g. use_currency("USD")."""
    def switch(code: str):
        monkeypatch.setenv("EXPENSE_CURRENCY", code)
        return importlib.reload(currency)

    return switch
