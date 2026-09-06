"""Actual cash value (ACV) of a line item from its replacement cost (RCV).

Straight-line depreciation by age using the per-category schedule loaded from
data/depreciation_schedule.csv (PLAT-388).
"""
from __future__ import annotations

from datetime import date

from tessera.adjudication.rounding import round_cents
from tessera.models import DepreciationRule, LineItem, LineValue

DAYS_PER_YEAR = 365


def age_in_years(purchase_date: date, loss_date: date) -> int:
    """Completed years of ownership at the loss date."""
    days = (loss_date - purchase_date).days
    return max(0, days // DAYS_PER_YEAR)


def depreciation_pct(rule: DepreciationRule, age_years: int) -> float:
    return rule.annual_pct * age_years


def value_item(item: LineItem, loss_date: date, schedule: dict[str, DepreciationRule]) -> LineValue:
    try:
        rule = schedule[item.category]
    except KeyError as exc:
        raise KeyError(f"no depreciation rule for category {item.category!r} (item {item.item_id})") from exc
    age = age_in_years(item.purchase_date, loss_date)
    pct = depreciation_pct(rule, age)
    # fully depreciated items are worth nothing, never a negative amount
    acv = max(0.0, round_cents(item.rcv * (100.0 - pct) / 100.0))
    return LineValue(item=item, age_years=age, depreciation_pct=pct, acv=acv)
