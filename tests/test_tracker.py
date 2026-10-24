from datetime import date

import pytest

from personal_finance_tracker import analytics
from personal_finance_tracker.db import ExpenseDB


@pytest.fixture
def db(tmp_path):
    db = ExpenseDB(tmp_path / "test.db")
    db.add_expense(date(2026, 9, 3), 12.50, "Food", "lunch")
    db.add_expense(date(2026, 9, 20), 40.00, "Transport", "fuel")
    db.add_expense(date(2026, 10, 1), 90.00, "Food", "groceries")
    db.add_expense(date(2026, 10, 15), 20.00, "Entertainment", "cinema")
    return db


def test_crud(db):
    df = db.get_expenses()
    assert len(df) == 4
    assert df.iloc[0]["description"] == "cinema"  # newest first

    expense_id = int(df.iloc[0]["id"])
    db.update_expense(expense_id, date(2026, 10, 16), 25.0, "Entertainment", "concert")
    row = db.get_expenses().set_index("id").loc[expense_id]
    assert row["amount"] == 25.0 and row["description"] == "concert"

    db.delete_expense(expense_id)
    assert expense_id not in db.get_expenses()["id"].values


def test_rejects_non_positive_amount(db):
    with pytest.raises(ValueError):
        db.add_expense(date(2026, 10, 1), 0, "Food")


def test_date_range_filter(db):
    df = db.get_expenses(date(2026, 10, 1), date(2026, 10, 31))
    assert sorted(df["description"]) == ["cinema", "groceries"]


def test_custom_category_listed(db):
    db.add_expense(date(2026, 10, 2), 5.0, "Pets")
    assert "Pets" in db.categories()


def test_aggregations(db):
    df = db.get_expenses()
    assert analytics.by_category(df).to_dict() == {
        "Food": 102.5, "Transport": 40.0, "Entertainment": 20.0
    }
    assert analytics.monthly_totals(df).to_dict() == {"2026-09": 52.5, "2026-10": 110.0}
    pivot = analytics.monthly_by_category(df)
    assert pivot.loc["2026-09", "Entertainment"] == 0.0
    assert pivot.loc["2026-10", "Food"] == 90.0


def test_budget_alerts(db):
    db.set_budget("Food", 100)
    db.set_budget("Entertainment", 24)
    db.set_budget("Transport", 50)
    db.set_budget("Food", 80)  # upsert
    october = db.get_expenses(date(2026, 10, 1), date(2026, 10, 31))
    levels = {a.category: a.level for a in analytics.budget_status(october, db.get_budgets())}
    assert levels == {"Food": "over", "Entertainment": "warning", "Transport": "ok"}


def test_empty_frames(tmp_path):
    df = ExpenseDB(tmp_path / "empty.db").get_expenses()
    assert analytics.by_category(df).empty
    assert analytics.monthly_totals(df).empty
    assert analytics.monthly_by_category(df).empty


def test_rounds_before_validating(db):
    for bad in (0.004, float("nan"), float("inf"), -1):
        with pytest.raises(ValueError):
            db.add_expense(date(2026, 10, 1), bad, "Food")
        with pytest.raises(ValueError):
            db.set_budget("Food", bad)


def test_month_boundaries(db):
    db.add_expense(date(2026, 10, 31), 1.0, "Food", "last day")
    db.add_expense(date(2026, 11, 1), 1.0, "Food", "next month")
    df = db.get_expenses(date(2026, 10, 1), date(2026, 10, 31))
    assert "last day" in df["description"].values
    assert "next month" not in df["description"].values


def test_gap_months_are_zero(tmp_path):
    db = ExpenseDB(tmp_path / "gap.db")
    db.add_expense(date(2026, 1, 5), 10.0, "Food")
    db.add_expense(date(2026, 4, 5), 20.0, "Transport")
    df = db.get_expenses()
    assert analytics.monthly_totals(df).to_dict() == {
        "2026-01": 10.0, "2026-02": 0.0, "2026-03": 0.0, "2026-04": 20.0
    }
    assert list(analytics.monthly_by_category(df).index) == ["2026-01", "2026-02", "2026-03", "2026-04"]


def test_budget_exactly_at_limit_is_over(tmp_path):
    db = ExpenseDB(tmp_path / "limit.db")
    for amount in (39.66, 6.39, 12.41, 40.16, 1.38):  # float sum is 99.99999999999999
        db.add_expense(date(2026, 10, 1), amount, "Food")
    [alert] = analytics.budget_status(db.get_expenses(), {"Food": 100})
    assert alert.level == "over"


def test_budget_with_no_spending(db):
    [alert] = analytics.budget_status(db.get_expenses(), {"Pets": 50})
    assert alert.spent == 0 and alert.level == "ok"


def test_csv_safe_neutralises_formulas(db):
    expense_id = db.add_expense(date(2026, 10, 2), 1.0, "@cmd", '=HYPERLINK("http://x","y")')
    out = analytics.csv_safe(db.get_expenses())
    row = out.set_index("id").loc[expense_id]
    assert row["description"].startswith("'=")
    assert row["category"] == "'@cmd"
    assert "groceries" in out["description"].values  # normal text untouched


def test_charts_render(db):
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure
    from personal_finance_tracker import charts

    db.add_expense(date(2026, 10, 3), 1.0, r"$\frac$")  # would be invalid mathtext
    db.add_expense(date(2026, 10, 3), 1.0, "_hidden")
    df = db.get_expenses()
    for fig in (
        charts.category_bar(analytics.by_category(df)),
        charts.monthly_bar(analytics.monthly_totals(df)),
        charts.monthly_stacked(analytics.monthly_by_category(df)),
    ):
        assert isinstance(fig, Figure)
        fig.canvas.draw()  # text is laid out (and mathtext parsed) at draw time
        plt.close(fig)


def test_currency_defaults_to_ugx():
    from personal_finance_tracker import currency

    assert currency.CODE == "UGX"
    assert currency.fmt(1234567.4) == "UGX 1,234,567"
    assert currency.number(12500) == "12,500"
    assert currency.number(12.5) == "13"  # half up, not banker's rounding
    assert currency.number(-0.4) == "0"  # no "-0"
    assert currency.signed(-3000) == "-UGX 3,000"
    assert currency.signed(2500) == "+UGX 2,500"
    assert currency.signed(-0.4) == "UGX 0"  # zero is unsigned
    assert currency.INPUT_MIN == 0.0  # so steps of 1,000 land on 7,000 not 7,001
    assert not currency.is_positive(0) and not currency.is_positive(0.4)
    assert currency.is_positive(0.5) and currency.is_positive(7000)


def test_is_positive_matches_db_in_usd(use_currency):
    currency = use_currency("USD")
    assert not currency.is_positive(0.004)
    assert currency.is_positive(0.005)
    assert currency.signed(0.004) == "USD 0.00" and currency.is_zero(0.004)


def test_chart_axes_show_full_amounts(tmp_path):
    import matplotlib.pyplot as plt
    from personal_finance_tracker import charts

    db = ExpenseDB(tmp_path / "big.db")
    db.add_expense(date(2026, 9, 1), 1_200_000, "Food")
    db.add_expense(date(2026, 10, 1), 3_500_000, "Housing")
    df = db.get_expenses()
    for fig, axis in (
        (charts.monthly_bar(analytics.monthly_totals(df)), "y"),
        (charts.monthly_stacked(analytics.monthly_by_category(df)), "y"),
        (charts.category_bar(analytics.by_category(df)), "x"),
    ):
        fig.canvas.draw()
        ax = fig.axes[0]
        ticks = ax.get_yticklabels() if axis == "y" else ax.get_xticklabels()
        labels = [t.get_text() for t in ticks]
        offset = (ax.yaxis if axis == "y" else ax.xaxis).get_offset_text().get_text()
        values = [int(label.replace(",", "")) for label in labels if label]
        assert max(values) >= 1_000_000 and offset == ""  # full amounts, no "1e6"
        plt.close(fig)


@pytest.mark.parametrize(
    "env, code, formatted, step, budget",
    [
        ("usd", "USD", "USD 1,234.50", 1.0, 100.0),
        ("JPY", "JPY", "JPY 1,235", 1000.0, 500_000.0),
        ("[x](http://e)", "UGX", "UGX 1,235", 1000.0, 500_000.0),  # invalid -> default
        ("", "UGX", "UGX 1,235", 1000.0, 500_000.0),
    ],
)
def test_currency_override(use_currency, env, code, formatted, step, budget):
    currency = use_currency(env)
    assert currency.CODE == code
    assert currency.fmt(1234.5) == formatted
    assert currency.STEP == step
    assert currency.DEFAULT_BUDGET == budget


def test_small_totals_get_whole_number_ticks():
    import matplotlib.pyplot as plt
    import pandas as pd
    from personal_finance_tracker import charts

    fig = charts.monthly_bar(pd.Series({"2026-09": 1.0, "2026-10": 3.0}))
    fig.canvas.draw()
    labels = [t.get_text() for t in fig.axes[0].get_yticklabels()]
    assert len(labels) == len(set(labels))  # no "1" for both 0.5 and 1
    plt.close(fig)


@pytest.mark.parametrize("scale", [1_234_567, 123_456_789, 2_500_000_000])
def test_category_axis_labels_round_and_not_overlapping(scale):
    import matplotlib.pyplot as plt
    import pandas as pd
    from personal_finance_tracker import charts

    fig = charts.category_bar(pd.Series({"Food": scale, "Rent": scale / 3, "Fun": scale / 7}))
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    ticks = [t for t in fig.axes[0].get_xticklabels() if t.get_text()]
    boxes = [t.get_window_extent(renderer) for t in ticks]
    assert not any(a.overlaps(b) for a, b in zip(boxes, boxes[1:]))
    step = fig.axes[0].get_xticks()[1] - fig.axes[0].get_xticks()[0]
    mantissa = step / 10 ** int(f"{step:e}".split("e")[1])
    assert mantissa in (1, 2, 2.5, 5)  # round steps, not 1.5/3/4/6/8
    plt.close(fig)


@pytest.mark.parametrize("total", [0.4, 0.9])
def test_sub_unit_totals_have_distinct_labels(total):
    import matplotlib.pyplot as plt
    import pandas as pd
    from personal_finance_tracker import charts

    for fig, axis in (
        (charts.monthly_bar(pd.Series({"2026-10": total})), "y"),
        (charts.category_bar(pd.Series({"Food": total})), "x"),
    ):
        fig.canvas.draw()
        ax = fig.axes[0]
        ticks = ax.get_yticklabels() if axis == "y" else ax.get_xticklabels()
        labels = [t.get_text() for t in ticks if t.get_text()]
        assert len(labels) == len(set(labels)), labels
        plt.close(fig)
