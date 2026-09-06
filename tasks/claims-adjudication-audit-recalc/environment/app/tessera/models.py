"""Domain models shared by every layer of the adjudication service."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class Policy:
    policy_id: str
    insured: str
    state: str
    dwelling_limit: float


@dataclass(frozen=True)
class PolicyVersion:
    """One in-force period of a policy (a new-business term, renewal or endorsement)."""

    version_id: str
    policy_id: str
    effective_from: date
    effective_to: Optional[date]  # None = open-ended
    contents_limit: float
    flat_deductible: float
    wind_hail_deductible_pct: Optional[float]


@dataclass(frozen=True)
class Sublimit:
    version_id: str
    category: str
    amount: float


@dataclass(frozen=True)
class Claim:
    claim_id: str
    policy_id: str
    occurrence_id: str
    claim_type: str  # original | supplemental
    peril: str
    loss_date: date
    fnol_date: date
    proof_of_loss_date: Optional[date]
    received_date: date
    status: str


@dataclass(frozen=True)
class LineItem:
    item_id: str
    claim_id: str
    category: str
    description: str
    rcv: float
    purchase_date: date


@dataclass(frozen=True)
class DepreciationRule:
    category: str
    annual_pct: float
    max_pct: float
    min_age_months: int


@dataclass(frozen=True)
class PromptPayRule:
    state: str
    clock_start: str  # proof_of_loss | fnol
    deadline_days: int
    day_type: str  # business | calendar
    annual_rate_pct: float
    interest_applies: bool


@dataclass
class PriorActivity:
    """What has already been paid / absorbed on a claim in earlier batches."""

    indemnity_paid: float = 0.0
    deductible_absorbed: float = 0.0


@dataclass
class LineValue:
    item: LineItem
    age_years: int
    depreciation_pct: float
    acv: float


@dataclass
class AdjudicationResult:
    claim: Claim
    status: str  # paid | zero_payment
    policy_version_id: Optional[str]
    gross_acv: float
    sublimit_reduction: float
    deductible: float
    deductible_applied: float
    indemnity: float
    days_late: int
    interest: float
    category_acv: dict[str, float] = field(default_factory=dict)
    line_values: list[LineValue] = field(default_factory=list)

    @property
    def payment_total(self) -> float:
        return self.indemnity + self.interest


@dataclass(frozen=True)
class Payment:
    payment_id: str
    claim_id: str
    occurrence_id: str
    batch: str
    payment_date: date
    policy_version_id: Optional[str]
    indemnity: float
    interest: float
    deductible_applied: float
    category_acv: dict[str, float]
