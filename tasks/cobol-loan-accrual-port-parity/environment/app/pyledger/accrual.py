"""Interest accrual for the period (3300-ACCRUE-INTEREST).

The COBOL computes in two stores:

    COMPUTE WS-DAILY-RATE = RT-ANNUAL-RATE(WS-TIER-IX) / WS-BASIS
    COMPUTE WS-ACCRUED ROUNDED = WS-NEW-BAL * WS-DAILY-RATE * WS-ACCR-DAYS

WS-DAILY-RATE is PIC 9V9(9) and the first COMPUTE is not ROUNDED, so the daily rate
is truncated to nine decimals before it is multiplied.  WS-ACCRUED is PIC S9(9)V99
and is ROUNDED (half away from zero).  Interest accrues only on a positive balance.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from .dates import days_360, days_between
from .models import RateTier
from .numeric import ZERO, divide, fit_pic, multiply, truncate

BASIS_360 = Decimal(360)
BASIS_365 = Decimal(365)
PRODUCT_MORTGAGE = "M"

DAILY_RATE_PIC = "9V9(9)"
ACCRUED_PIC = "S9(9)V99"
ACCR_DAYS_PIC = "S9(5)"


def basis_for(product: str) -> Decimal:
    return BASIS_360 if product == PRODUCT_MORTGAGE else BASIS_365


def accrual_days(product: str, last_accrual: date, asof: date) -> int:
    if product == PRODUCT_MORTGAGE:
        days = days_360(last_accrual, asof)
    else:
        days = days_between(last_accrual, asof)
    return int(fit_pic(Decimal(days), ACCR_DAYS_PIC))


def daily_rate(tier: RateTier, product: str) -> Decimal:
    """WS-DAILY-RATE: annual rate / basis, truncated to the PIC 9V9(9) scale."""
    return fit_pic(divide(tier.annual_rate, basis_for(product)), DAILY_RATE_PIC)


def accrued_interest(balance: Decimal, rate_per_day: Decimal, days: int) -> Decimal:
    """WS-ACCRUED ROUNDED = balance * daily rate * days, or zero when the balance is not positive."""
    if balance <= ZERO:
        return ZERO
    product = multiply(balance, rate_per_day, Decimal(days))
    return fit_pic(product, ACCRUED_PIC, rounded_store=True)


def accrue(balance: Decimal, tier: RateTier, product: str, last_accrual: date, asof: date):
    """Return (daily_rate, accrual_days, accrued_interest) for one account."""
    days = accrual_days(product, last_accrual, asof)
    rate = daily_rate(tier, product)
    interest = accrued_interest(balance, rate, days)
    return rate, days, interest


__all__ = ["accrue", "accrual_days", "accrued_interest", "basis_for", "daily_rate", "truncate"]
