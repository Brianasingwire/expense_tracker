"""Currency display settings. Defaults to Ugandan shillings; override with EXPENSE_CURRENCY.

Settings are read once at import; tests reload this module to switch currencies.
"""

from __future__ import annotations

import os
import re
from decimal import ROUND_HALF_UP, Decimal

DEFAULT_CODE = "UGX"

_code = os.environ.get("EXPENSE_CURRENCY", DEFAULT_CODE).strip().upper()
# Only accept an ISO 4217-style code; anything else (typos, markup) falls back to UGX.
CODE = _code if re.fullmatch(r"[A-Z]{3}", _code) else DEFAULT_CODE

# Currencies with no minor unit in everyday use are shown and entered as whole numbers.
_ZERO_DECIMAL = {"UGX", "RWF", "BIF", "JPY", "KRW"}
DECIMALS = 0 if CODE in _ZERO_DECIMAL else 2

INPUT_FORMAT = f"%.{DECIMALS}f"
MIN_AMOUNT = 1.0 if DECIMALS == 0 else 0.01
STEP = 1000.0 if DECIMALS == 0 else 1.0
DEFAULT_BUDGET = 500_000.0 if DECIMALS == 0 else 100.0


def number(amount: float) -> str:
    """Amount with thousands separators and the currency's decimals, rounded half up."""
    rounded = Decimal(str(amount)).quantize(Decimal(1).scaleb(-DECIMALS), ROUND_HALF_UP)
    if rounded == 0:
        rounded = abs(rounded)  # avoid "-0"
    return f"{rounded:,.{DECIMALS}f}"


def fmt(amount: float) -> str:
    """Amount with the currency code, e.g. 'UGX 12,500'."""
    return f"{CODE} {number(amount)}"


def signed(amount: float) -> str:
    """Signed amount with the sign first ('-UGX 3,000'), so st.metric picks the right arrow."""
    magnitude = number(abs(amount))
    sign = "-" if amount < 0 and magnitude != number(0) else "+"
    return f"{sign}{CODE} {magnitude}"


def input_min(current: float | None = None) -> float:
    """number_input min_value that never rejects an already-stored smaller amount."""
    return MIN_AMOUNT if current is None else min(MIN_AMOUNT, current)
