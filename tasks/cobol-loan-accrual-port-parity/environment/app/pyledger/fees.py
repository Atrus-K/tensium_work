"""Days-late determination and late-fee assessment (3400-DAYS-LATE / 3500-ASSESS-LATE-FEE)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from .dates import BusinessCalendar, days_between
from .models import Account, RateTier
from .numeric import ZERO, rounded

NEW_ACCOUNT_WINDOW_DAYS = 90  # no late fee while the account is 90 days old or younger


def days_late(account: Account, paid: Decimal, asof: date, calendar: BusinessCalendar) -> int:
    """Days late counted from the (business-day rolled) due date; zero when paid in full or not yet due."""
    rolled_due = calendar.roll_forward(account.due_date)
    # the due date itself counts as the first day late
    late = days_between(rolled_due, asof) + 1
    if late < 0:
        late = 0
    if paid >= account.payment_due:
        late = 0
    return late


def is_new_account(account: Account, asof: date) -> bool:
    return days_between(account.orig_date, asof) <= NEW_ACCOUNT_WINDOW_DAYS


def late_fee(account: Account, tier: RateTier, late: int, asof: date) -> Decimal:
    """Tier percentage of the payment due, rounded, then floored/capped by the tier fee bounds.

    Assessed once the grace period is used up and the account is older than the
    new-account window.
    """
    if late < account.grace_days:
        return ZERO
    if is_new_account(account, asof):
        return ZERO
    fee = rounded(float(account.payment_due) * float(tier.late_pct), 2)
    if fee < tier.fee_min:
        fee = tier.fee_min
    if fee > tier.fee_max:
        fee = tier.fee_max
    return fee
