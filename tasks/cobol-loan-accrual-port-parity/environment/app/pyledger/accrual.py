"""Interest accrual for the period (3300-ACCRUE-INTEREST).

    accrued = balance * annual rate / basis * days, ROUNDED to cents

Mortgage products use a 360-day basis with 30/360 day counts; everything else uses
actual days over 365.  Interest accrues only on a positive balance.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from .dates import days_360, days_between
from .models import RateTier
from .numeric import ZERO, divide, rounded

BASIS_360 = 360
BASIS_365 = 365
PRODUCT_MORTGAGE = "M"


def basis_for(product: str) -> int:
    return BASIS_360 if product == PRODUCT_MORTGAGE else BASIS_365


def accrual_days(product: str, last_accrual: date, asof: date) -> int:
    if product == PRODUCT_MORTGAGE:
        return days_360(last_accrual, asof)
    return days_between(last_accrual, asof)


def daily_rate(tier: RateTier, product: str) -> Decimal:
    """Annual rate over the basis; the writer fits it to LO-DAILY-RATE (PIC 9V9(9))."""
    return divide(tier.annual_rate, basis_for(product))


def accrued_interest(balance: Decimal, tier: RateTier, product: str, days: int) -> Decimal:
    if balance <= ZERO:
        return ZERO
    return rounded(float(balance) * float(tier.annual_rate) / basis_for(product) * days, 2)


def accrue(balance: Decimal, tier: RateTier, product: str, last_accrual: date, asof: date):
    """Return (daily_rate, accrual_days, accrued_interest) for one account."""
    days = accrual_days(product, last_accrual, asof)
    rate = daily_rate(tier, product)
    interest = accrued_interest(balance, tier, product, days)
    return rate, days, interest


__all__ = ["accrue", "accrual_days", "accrued_interest", "basis_for", "daily_rate"]
