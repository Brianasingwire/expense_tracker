"""Matplotlib figures rendered by the Streamlit app."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # headless backend; Streamlit renders the figure objects

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.figure import Figure

from personal_finance_tracker import currency

# Category names are user text: don't let "$...$" be parsed as mathtext (it can raise).
plt.rcParams["text.parse_math"] = False

ACCENT = "#e8458b"
PALETTE = plt.get_cmap("tab10").colors


def _style(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)


def monthly_bar(totals: pd.Series) -> Figure:
    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(totals.index, totals.values, color=ACCENT)
    ax.bar_label(bars, labels=[currency.number(v) for v in totals.values], fontsize=8, padding=2)
    ax.set_title("Monthly spending")
    ax.set_ylabel(f"Amount ({currency.CODE})")
    ax.tick_params(axis="x", rotation=45)
    _style(ax)
    fig.tight_layout()
    return fig


def category_bar(totals: pd.Series) -> Figure:
    """Horizontal bars (easier to compare than a pie), largest at the top."""
    data = totals.sort_values()
    fig, ax = plt.subplots(figsize=(8, max(2.5, 0.45 * len(data) + 1)))
    bars = ax.barh(data.index, data.values, color=ACCENT)
    ax.bar_label(bars, labels=[currency.number(v) for v in data.values], fontsize=8, padding=3)
    ax.set_title("Spending by category")
    ax.set_xlabel(f"Amount ({currency.CODE})")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", alpha=0.3)
    ax.set_axisbelow(True)
    fig.tight_layout()
    return fig


def monthly_stacked(pivot: pd.DataFrame) -> Figure:
    fig, ax = plt.subplots(figsize=(8, 4))
    bottom = None
    for i, category in enumerate(pivot.columns):
        values = pivot[category].values
        # Matplotlib hides legend labels starting with "_"; a leading space keeps them.
        label = f" {category}" if str(category).startswith("_") else category
        ax.bar(pivot.index, values, bottom=bottom, label=label,
               color=PALETTE[i % len(PALETTE)])
        bottom = values if bottom is None else bottom + values
    ax.set_title("Monthly spending by category")
    ax.set_ylabel(f"Amount ({currency.CODE})")
    ax.tick_params(axis="x", rotation=45)
    ax.legend(fontsize=8, bbox_to_anchor=(1.02, 1), loc="upper left", frameon=False)
    _style(ax)
    fig.tight_layout()
    return fig
