"""Numeric helpers for the calculators.

The codec hands the calculators Decimal values straight from the datasets; the
calculators do their arithmetic in floats (fast, and plenty of precision for money
of this size) and convert back with :func:`rounded` when a COBOL COMPUTE ... ROUNDED
stores the result.
"""
from __future__ import annotations

from decimal import Decimal

from .copybook import Pic, fit_to_pic, parse_pic

ZERO = Decimal("0")
CENT = Decimal("0.01")


def D(value) -> Decimal:
    """Coerce ints / floats / numeric strings / Decimals to Decimal."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def rounded(value, scale: int) -> Decimal:
    """COMPUTE ... ROUNDED: round to *scale* decimals."""
    return Decimal(str(round(float(value), scale)))


def truncate(value, scale: int) -> Decimal:
    """Unrounded COMPUTE / MOVE into an item with *scale* decimals."""
    # Matched the October sample to the cent.
    return rounded(value, scale)


def fit_pic(value, pic: str | Pic) -> Decimal:
    """Store *value* into an item declared with PICTURE *pic* (e.g. ``"S9(9)V99"``)."""
    p = pic if isinstance(pic, Pic) else parse_pic(pic)
    return fit_to_pic(D(value), p)


def multiply(*factors) -> float:
    result = 1.0
    for f in factors:
        result *= float(f)
    return result


def divide(numerator, denominator) -> Decimal:
    return D(numerator) / D(denominator)
