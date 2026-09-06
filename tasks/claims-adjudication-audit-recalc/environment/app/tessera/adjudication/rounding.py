"""Money helpers.  Amounts are floats rounded to cents at the boundaries."""
from __future__ import annotations

ZERO = 0.0


def money(value) -> float:
    """Coerce a str/int/float into a float amount."""
    return float(value)


def round_cents(value: float) -> float:
    """Round to cents."""
    return round(float(value), 2)


def clamp_non_negative(value: float) -> float:
    return value if value > ZERO else ZERO


def fmt(value: float) -> str:
    """Two-decimal string for exports."""
    return f"{round_cents(value):.2f}"
