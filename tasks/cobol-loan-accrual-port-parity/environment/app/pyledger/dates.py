"""Date handling mirroring the LNACCR01 date paragraphs.

* YYMMDD fields use the program's century window (2000-CENTURY-WINDOW):
  a two-digit year above 49 belongs to the 1900s, otherwise to the 2000s.
* Day differences use FUNCTION INTEGER-OF-DATE arithmetic (exclusive: the
  difference between a date and the following day is 1).
* Mortgage products accrue on a 30/360 (US) basis (2300-DAYS-360); other products
  on actual days (2200-DAYS-ACTUAL).
* Due dates falling on a weekend or bank holiday roll forward to the next
  business day (2400-ROLL-BUSINESS-DAY).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

CENTURY_PIVOT = 49  # YY > 49 -> 19YY, else 20YY


def from_yymmdd(value: Decimal | int | str) -> date:
    text = f"{int(value):06d}"
    yy, mm, dd = int(text[0:2]), int(text[2:4]), int(text[4:6])
    century = 1900 if yy > CENTURY_PIVOT else 2000
    return date(century + yy, mm, dd)


def parse_asof(text: str) -> date:
    """Accept YYYY-MM-DD (CLI) or YYYYMMDD (JCL PARM style)."""
    digits = text.replace("-", "")
    if len(digits) != 8 or not digits.isdigit():
        raise ValueError(f"as-of date must be YYYY-MM-DD, got {text!r}")
    return date(int(digits[0:4]), int(digits[4:6]), int(digits[6:8]))


def to_yyyymmdd(d: date) -> int:
    return d.year * 10000 + d.month * 100 + d.day


_EPOCH = date(1600, 12, 31)  # INTEGER-OF-DATE(1601-01-01) = 1


def integer_of_date(d: date) -> int:
    return (d - _EPOCH).days


def days_between(start: date, end: date) -> int:
    """INTEGER-OF-DATE(end) - INTEGER-OF-DATE(start); negative if end precedes start."""
    return integer_of_date(end) - integer_of_date(start)


def days_360(start: date, end: date) -> int:
    """30/360 US day count with both end-of-month clamps."""
    d1, d2 = start.day, end.day
    if d1 == 31:
        d1 = 30
    if d2 == 31 and d1 >= 30:
        d2 = 30
    return 360 * (end.year - start.year) + 30 * (end.month - start.month) + (d2 - d1)


class BusinessCalendar:
    """Weekend + holiday calendar loaded from HOLIDAYS.dat (YYYYMMDD DESCRIPTION lines)."""

    def __init__(self, holidays: set[date]):
        self.holidays = frozenset(holidays)

    @classmethod
    def load(cls, path: str | Path) -> "BusinessCalendar":
        holidays: set[date] = set()
        with open(path, "r", encoding="ascii") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line.strip() or line.startswith("*"):
                    continue
                token = line[:8]
                holidays.add(date(int(token[0:4]), int(token[4:6]), int(token[6:8])))
        return cls(holidays)

    def is_business_day(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self.holidays

    def roll_forward(self, d: date) -> date:
        while not self.is_business_day(d):
            d += timedelta(days=1)
        return d
