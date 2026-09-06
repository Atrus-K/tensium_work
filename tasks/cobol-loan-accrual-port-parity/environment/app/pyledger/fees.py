"""Days-late determination and late-fee assessment (3400-DAYS-LATE / 3500-ASSESS-LATE-FEE)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from .dates import BusinessCalendar, days_between
from .models import Account, RateTier
from .numeric import ZERO, fit_pic, multiply

LATE_FEE_PIC = "9(7)V99"
NEW_ACCOUNT_WINDOW_DAYS = 90  # no late fee while the account is 90 days old or younger


def days_late(account: Account, paid: Decimal, asof: date, calendar: BusinessCalendar) -> int:
    """Whole days from the rolled due date to the as-of date; zero when paid in full or not yet due.

    COMPUTE WS-DAYS-LATE = INTEGER-OF-DATE(as-of) - INTEGER-OF-DATE(rolled due date)
    """
    rolled_due = calendar.roll_forward(account.due_date)
    late = days_between(rolled_due, asof)
    if late < 0:
        late = 0
    if paid >= account.payment_due:
        late = 0
    return late


def is_new_account(account: Account, asof: date) -> bool:
    return days_between(account.orig_date, asof) <= NEW_ACCOUNT_WINDOW_DAYS


def late_fee(account: Account, tier: RateTier, late: int, asof: date) -> Decimal:
    """Tier percentage of the payment due, ROUNDED, then floored/capped by the tier fee bounds.

    The fee is assessed only when the account is past its grace period
    (days late strictly greater than LM-GRACE-DAYS), not flagged for waiver, and
    older than the new-account window.
    """
    if late <= account.grace_days:
        return ZERO
    if account.waive_late_fee:
        return ZERO
    if is_new_account(account, asof):
        return ZERO
    fee = fit_pic(multiply(account.payment_due, tier.late_pct), LATE_FEE_PIC, rounded_store=True)
    if fee < tier.fee_min:
        fee = tier.fee_min
    if fee > tier.fee_max:
        fee = tier.fee_max
    return fee
