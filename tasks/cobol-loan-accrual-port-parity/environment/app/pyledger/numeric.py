"""COBOL numeric semantics for the calculators.

LNACCR01 is compiled with ARITH(EXTEND): the intermediate result of a COMPUTE is
exact and only the store into the receiving item loses precision.  Two kinds of
store exist:

* ``COMPUTE X ROUNDED = ...`` -- rounds half away from zero to X's scale;
* ``COMPUTE X = ...`` / ``MOVE`` -- truncates (toward zero) to X's scale.

Both then drop any high-order digits that do not fit the PICTURE.  All money and
rate arithmetic in the port is done with :class:`decimal.Decimal` so that these
rules can be applied exactly; never route a value through ``float``.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, localcontext

from .copybook import Pic, fit_to_pic, parse_pic

ZERO = Decimal("0")
CENT = Decimal("0.01")

# Enough precision for 13-digit money * 10-digit rate * 3-digit day counts.
_PRECISION = 40


def D(value) -> Decimal:
    """Coerce ints / numeric strings / Decimals to Decimal without going through float."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        raise TypeError("float values are not allowed in COBOL arithmetic; pass str or Decimal")
    return Decimal(value)


def rounded(value: Decimal, scale: int) -> Decimal:
    """COMPUTE ... ROUNDED: half away from zero at *scale* decimals."""
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        return D(value).quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_UP)


def truncate(value: Decimal, scale: int) -> Decimal:
    """Unrounded COMPUTE / MOVE: drop low-order digits beyond *scale* (toward zero)."""
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        return D(value).quantize(Decimal(1).scaleb(-scale), rounding=ROUND_DOWN)


def fit_pic(value: Decimal, pic: str | Pic, rounded_store: bool = False) -> Decimal:
    """Store *value* into an item declared with PICTURE *pic* (e.g. ``"S9(9)V99"``)."""
    p = pic if isinstance(pic, Pic) else parse_pic(pic)
    v = rounded(D(value), p.scale) if rounded_store else D(value)
    return fit_to_pic(v, p)


def multiply(*factors: Decimal) -> Decimal:
    """Exact product of Decimal factors (the intermediate result of a COMPUTE)."""
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        result = Decimal(1)
        for f in factors:
            result *= D(f)
        return result


def divide(numerator: Decimal, denominator: Decimal) -> Decimal:
    """Exact-enough quotient (40 significant digits) for a subsequent PIC store."""
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        return D(numerator) / D(denominator)
