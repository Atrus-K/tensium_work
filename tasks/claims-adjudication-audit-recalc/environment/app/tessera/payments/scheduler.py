"""Prompt-pay deadline and statutory interest."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from tessera.adjudication.rounding import round_cents
from tessera.calendar.business_days import add_business_days, add_calendar_days
from tessera.models import Claim, PromptPayRule

DAYS_PER_YEAR = 365


@dataclass(frozen=True)
class PromptPayOutcome:
    clock_start: Optional[date]
    deadline: Optional[date]
    days_late: int
    interest: float


def payment_deadline(claim: Claim, rule: PromptPayRule) -> date:
    """Deadline counted from first notice of loss per the state's day type."""
    if rule.day_type == "business":
        return add_business_days(claim.fnol_date, rule.deadline_days)
    return add_calendar_days(claim.fnol_date, rule.deadline_days)


def interest_amount(indemnity: float, rule: PromptPayRule, days_late: int) -> float:
    if days_late <= 0 or indemnity <= 0:
        return 0.0
    daily_rate = rule.annual_rate_pct / 100.0 / DAYS_PER_YEAR
    return round_cents(indemnity * daily_rate * days_late)


def evaluate(claim: Claim, rule: PromptPayRule, indemnity: float, payment_date: date) -> PromptPayOutcome:
    deadline = payment_deadline(claim, rule)
    days_late = max(0, (payment_date - deadline).days)
    return PromptPayOutcome(claim.fnol_date, deadline, days_late, interest_amount(indemnity, rule, days_late))
