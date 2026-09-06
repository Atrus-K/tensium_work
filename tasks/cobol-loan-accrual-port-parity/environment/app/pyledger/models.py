"""Plain data holders shared by the batch stages."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class RateTier:
    index: int  # 1-based, as in the COBOL OCCURS table
    upper_balance: Decimal
    annual_rate: Decimal
    late_pct: Decimal
    fee_min: Decimal
    fee_max: Decimal


@dataclass
class Transaction:
    account: int
    post_date: date
    seq: int
    tran_type: str  # 'P' payment, 'R' reversal
    amount: Decimal
    voided: bool
    channel: str


@dataclass
class Account:
    account: int
    name: str
    product: str
    status: str
    orig_date: date
    due_date: date
    last_accrual_date: date
    principal: Decimal
    payment_due: Decimal
    grace_days: int
    branch: str
    waive_late_fee: bool
    officer: str

    @property
    def is_closed(self) -> bool:
        return self.status == "Z"


@dataclass
class AccountResult:
    account: Account
    new_balance: Decimal
    paid_amount: Decimal
    tier: RateTier
    daily_rate: Decimal
    accrual_days: int
    accrued_interest: Decimal
    days_late: int
    late_fee: Decimal
    status_letter: str


@dataclass
class BatchTotals:
    record_count: int = 0
    hash_total: int = 0
    total_accrued: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    total_balance: Decimal = Decimal("0")
    skipped_closed: int = 0
    results: list[AccountResult] = field(default_factory=list)
