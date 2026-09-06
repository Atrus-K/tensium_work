"""Business-day arithmetic (added for the SLA dashboard, PLAT-340)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

WEEKEND = (5, 6)


def is_business_day(day: date) -> bool:
    return day.weekday() not in WEEKEND


def add_business_days(start: date, n: int, holidays: Iterable[date] = ()) -> date:
    """The date reached after counting *n* business days from *start*."""
    if n < 0:
        raise ValueError("n must be non-negative")
    day = start
    counted = 0
    while True:
        if is_business_day(day):
            counted += 1
        if counted >= n:
            return day
        day += timedelta(days=1)


def add_calendar_days(start: date, n: int) -> date:
    return start + timedelta(days=n)


def business_days_between(start: date, end: date) -> int:
    """Number of business days from *start* to *end* inclusive."""
    count = 0
    day = start
    while day <= end:
        if is_business_day(day):
            count += 1
        day += timedelta(days=1)
    return count
