#!/usr/bin/env bash
# Reference fix for AUD-2024-117: policy-version lookup by loss date with half-open
# intervals and no fallback; per-occurrence sublimits/deductible/limit netted against the
# ledger; month-based capped depreciation; per-state prompt-pay clock with holiday-aware
# business days; Decimal ROUND_HALF_UP money everywhere.
set -euo pipefail
cd /app

cat > tessera/adjudication/engine.py <<'PYEOF'
"""Core adjudication of one claim (docs/adjudication_rules.md sections 1-6).

Order of operations for a covered claim:
  1. value every line item at ACV (rounded per line);
  2. aggregate ACV per category and apply the version's per-occurrence category
     sublimits, net of what earlier claims on the occurrence already used;
  3. apply whatever is left of the occurrence deductible (flat or wind/hail %);
  4. cap at the Coverage C limit net of indemnity already paid on the occurrence;
  5. prompt-pay interest on the indemnity.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import date
from decimal import Decimal

from tessera.adjudication.rounding import ZERO, clamp_non_negative, round_cents
from tessera.models import AdjudicationResult, Claim, LineValue, OccurrencePrior, PolicyVersion, PromptPayRule
from tessera.payments import ledger, scheduler
from tessera.policy import coverage, lookup
from tessera.storage import db
from tessera.valuation.depreciation import value_item

log = logging.getLogger("tessera.engine")


class Adjudicator:
    """Holds the reference tables for a batch run and adjudicates claims one at a time."""

    def __init__(self, conn: sqlite3.Connection, payment_date: date):
        self.conn = conn
        self.payment_date = payment_date
        self.schedule = db.get_depreciation_schedule(conn)
        self.prompt_pay_rules = db.get_prompt_pay_rules(conn)
        self.holidays = db.get_holidays(conn)

    # ------------------------------------------------------------------ steps
    def value_lines(self, claim: Claim) -> list[LineValue]:
        return [value_item(item, claim.loss_date, self.schedule) for item in db.get_line_items(self.conn, claim.claim_id)]

    @staticmethod
    def aggregate_by_category(lines: list[LineValue]) -> dict[str, Decimal]:
        totals: dict[str, Decimal] = {}
        for lv in lines:
            totals[lv.item.category] = totals.get(lv.item.category, ZERO) + lv.acv
        return totals

    @staticmethod
    def apply_sublimits(per_category: dict[str, Decimal], sublimits: dict[str, Decimal], prior: OccurrencePrior) -> dict[str, Decimal]:
        """Attribute to this claim only the headroom left under each category sublimit."""
        attributed: dict[str, Decimal] = {}
        for category, amount in per_category.items():
            cap = sublimits.get(category)
            if cap is None:
                attributed[category] = amount
                continue
            headroom = clamp_non_negative(cap - prior.category_acv.get(category, ZERO))
            attributed[category] = min(amount, headroom)
        return attributed

    def prompt_pay_rule(self, state: str) -> PromptPayRule:
        try:
            return self.prompt_pay_rules[state]
        except KeyError as exc:
            raise KeyError(f"no prompt-pay rule configured for state {state!r}") from exc

    # ------------------------------------------------------------------ main
    def adjudicate(self, claim: Claim) -> AdjudicationResult:
        policy = db.get_policy(self.conn, claim.policy_id)
        versions = db.get_policy_versions(self.conn, claim.policy_id)
        version = lookup.find_version(versions, claim.loss_date)
        if version is None:
            log.warning("%s: no policy version of %s in force on loss date %s; claim not covered",
                        claim.claim_id, claim.policy_id, claim.loss_date.isoformat())
            return AdjudicationResult(claim, "no_coverage", None, ZERO, ZERO, ZERO, ZERO, ZERO, 0, ZERO)

        lines = self.value_lines(claim)
        per_category = self.aggregate_by_category(lines)
        gross = sum(per_category.values(), ZERO)

        prior = ledger.occurrence_prior(self.conn, claim.occurrence_id)
        sublimits = coverage.sublimit_map(db.get_sublimits(self.conn, version.version_id))
        attributed = self.apply_sublimits(per_category, sublimits, prior)
        covered = sum(attributed.values(), ZERO)
        sublimit_reduction = gross - covered

        deductible = coverage.deductible_for(version, policy, claim.peril)
        deductible_remaining = clamp_non_negative(deductible - prior.deductible_absorbed)
        deductible_applied = min(deductible_remaining, covered)

        limit_headroom = clamp_non_negative(coverage.contents_limit(version) - prior.indemnity_paid)
        indemnity = round_cents(min(covered - deductible_applied, limit_headroom))

        rule = self.prompt_pay_rule(policy.state)
        outcome = scheduler.evaluate(claim, rule, indemnity, self.payment_date, self.holidays)

        status = "paid" if indemnity > ZERO else "zero_payment"
        log.info(
            "%s: version=%s gross=%s sublimit_reduction=%s deductible=%s applied=%s indemnity=%s interest=%s (%d days late, deadline %s)",
            claim.claim_id, version.version_id, gross, sublimit_reduction, deductible, deductible_applied, indemnity,
            outcome.interest, outcome.days_late, outcome.deadline.isoformat() if outcome.deadline else "n/a",
        )
        return AdjudicationResult(
            claim=claim,
            status=status,
            policy_version_id=version.version_id,
            gross_acv=round_cents(gross),
            sublimit_reduction=round_cents(sublimit_reduction),
            deductible=deductible,
            deductible_applied=round_cents(deductible_applied),
            indemnity=indemnity,
            days_late=outcome.days_late,
            interest=outcome.interest,
            category_acv={k: round_cents(v) for k, v in attributed.items()},
            line_values=lines,
        )


def run_batch(conn: sqlite3.Connection, batch: str, as_of: date) -> list[AdjudicationResult]:
    """Adjudicate every claim of *batch* and record payments, atomically and idempotently."""
    adjudicator = Adjudicator(conn, payment_date=as_of)
    results: list[AdjudicationResult] = []
    with conn:
        removed = ledger.clear_batch(conn, batch)
        if removed:
            log.info("batch %s: replaced %d payment(s) from an earlier run", batch, removed)
        for claim in db.get_claims_for_batch(conn, batch):
            result = adjudicator.adjudicate(claim)
            results.append(result)
            if result.status != "no_coverage":
                ledger.record_payment(conn, ledger.build_payment(result, batch, as_of))
    return results
PYEOF

cat > tessera/adjudication/rounding.py <<'PYEOF'
"""Money helpers.  Every monetary figure in the engine is a Decimal rounded
half-up to cents (docs/adjudication_rules.md section 7)."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value) -> Decimal:
    """Coerce a str/int/Decimal into a Decimal without going through float."""
    if isinstance(value, float):
        raise TypeError("floats are not allowed for money; pass str or Decimal")
    return Decimal(str(value))


def round_cents(value: Decimal) -> Decimal:
    """Round to cents, half away from zero (ROUND_HALF_UP)."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def clamp_non_negative(value: Decimal) -> Decimal:
    return value if value > ZERO else ZERO


def fmt(value: Decimal) -> str:
    """Two-decimal string for exports."""
    return f"{round_cents(value):.2f}"
PYEOF

cat > tessera/calendar/business_days.py <<'PYEOF'
"""Business-day arithmetic used by prompt-pay deadlines.

A business day is a weekday that is not in the holidays table.  When adding N
business days to a start date the start date itself is never counted.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

WEEKEND = (5, 6)


def is_business_day(day: date, holidays: Iterable[date]) -> bool:
    return day.weekday() not in WEEKEND and day not in set(holidays)


def add_business_days(start: date, n: int, holidays: Iterable[date]) -> date:
    """The date N business days after *start* (start not counted)."""
    if n < 0:
        raise ValueError("n must be non-negative")
    hol = set(holidays)
    current = start
    remaining = n
    while remaining > 0:
        current += timedelta(days=1)
        if is_business_day(current, hol):
            remaining -= 1
    return current


def add_calendar_days(start: date, n: int) -> date:
    return start + timedelta(days=n)


def business_days_between(start: date, end: date, holidays: Iterable[date]) -> int:
    """Number of business days in (start, end]."""
    hol = set(holidays)
    count = 0
    current = start
    while current < end:
        current += timedelta(days=1)
        if is_business_day(current, hol):
            count += 1
    return count
PYEOF

cat > tessera/models.py <<'PYEOF'
"""Domain models shared by every layer of the adjudication service."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class Policy:
    policy_id: str
    insured: str
    state: str
    dwelling_limit: Decimal


@dataclass(frozen=True)
class PolicyVersion:
    """One in-force period of a policy (a new-business term, renewal or endorsement)."""

    version_id: str
    policy_id: str
    effective_from: date
    effective_to: Optional[date]  # None = open-ended
    contents_limit: Decimal
    flat_deductible: Decimal
    wind_hail_deductible_pct: Optional[Decimal]


@dataclass(frozen=True)
class Sublimit:
    version_id: str
    category: str
    amount: Decimal


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
    rcv: Decimal
    purchase_date: date


@dataclass(frozen=True)
class DepreciationRule:
    category: str
    annual_pct: Decimal
    max_pct: Decimal
    min_age_months: int


@dataclass(frozen=True)
class PromptPayRule:
    state: str
    clock_start: str  # proof_of_loss | fnol
    deadline_days: int
    day_type: str  # business | calendar
    annual_rate_pct: Decimal
    interest_applies: bool


@dataclass
class OccurrencePrior:
    """What has already been paid / absorbed on an occurrence before the current claim."""

    indemnity_paid: Decimal = Decimal("0.00")
    deductible_absorbed: Decimal = Decimal("0.00")
    category_acv: dict[str, Decimal] = field(default_factory=dict)


@dataclass
class LineValue:
    item: LineItem
    age_months: int
    depreciation_pct: Decimal
    acv: Decimal


@dataclass
class AdjudicationResult:
    claim: Claim
    status: str  # paid | zero_payment | no_coverage
    policy_version_id: Optional[str]
    gross_acv: Decimal
    sublimit_reduction: Decimal
    deductible: Decimal
    deductible_applied: Decimal
    indemnity: Decimal
    days_late: int
    interest: Decimal
    category_acv: dict[str, Decimal] = field(default_factory=dict)
    line_values: list[LineValue] = field(default_factory=list)

    @property
    def payment_total(self) -> Decimal:
        return self.indemnity + self.interest


@dataclass(frozen=True)
class Payment:
    payment_id: str
    claim_id: str
    occurrence_id: str
    batch: str
    payment_date: date
    policy_version_id: Optional[str]
    indemnity: Decimal
    interest: Decimal
    deductible_applied: Decimal
    category_acv: dict[str, Decimal]
PYEOF

cat > tessera/payments/ledger.py <<'PYEOF'
"""Payment ledger: occurrence-scoped history and idempotent payment writes.

Everything the engine needs to know about *prior* activity on an occurrence
(indemnity already paid, deductible already absorbed, per-category ACV already
attributed) comes from the payments table, whether those payments were loaded
from history or created earlier in the same batch run.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from decimal import Decimal

from tessera.adjudication.rounding import ZERO, fmt, round_cents
from tessera.models import AdjudicationResult, OccurrencePrior, Payment


def _d(value) -> Decimal:
    return round_cents(Decimal(str(value)))


def occurrence_prior(conn: sqlite3.Connection, occurrence_id: str) -> OccurrencePrior:
    """Aggregate every payment already recorded against *occurrence_id*."""
    prior = OccurrencePrior()
    rows = conn.execute(
        "SELECT indemnity, deductible_applied, category_acv FROM payments WHERE occurrence_id = ? ORDER BY payment_id",
        (occurrence_id,),
    ).fetchall()
    for r in rows:
        prior.indemnity_paid += _d(r["indemnity"])
        prior.deductible_absorbed += _d(r["deductible_applied"])
        for category, amount in json.loads(r["category_acv"] or "{}").items():
            prior.category_acv[category] = prior.category_acv.get(category, ZERO) + _d(amount)
    return prior


def clear_batch(conn: sqlite3.Connection, batch: str) -> int:
    """Remove every payment produced by an earlier run of *batch* so a re-run
    starts from the same ledger state (re-runs replace, never duplicate)."""
    cur = conn.execute("DELETE FROM payments WHERE batch = ?", (batch,))
    return cur.rowcount


def payment_id_for(claim_id: str, batch: str) -> str:
    return f"PAY-{batch}-{claim_id}"


def build_payment(result: AdjudicationResult, batch: str, payment_date: date) -> Payment:
    return Payment(
        payment_id=payment_id_for(result.claim.claim_id, batch),
        claim_id=result.claim.claim_id,
        occurrence_id=result.claim.occurrence_id,
        batch=batch,
        payment_date=payment_date,
        policy_version_id=result.policy_version_id,
        indemnity=round_cents(result.indemnity),
        interest=round_cents(result.interest),
        deductible_applied=round_cents(result.deductible_applied),
        category_acv=dict(result.category_acv),
    )


def record_payment(conn: sqlite3.Connection, payment: Payment) -> None:
    """Upsert on (claim_id, batch)."""
    conn.execute(
        """
        INSERT INTO payments (payment_id, claim_id, occurrence_id, batch, payment_date, policy_version_id,
                              indemnity, interest, deductible_applied, category_acv)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(claim_id, batch) DO UPDATE SET
            payment_date = excluded.payment_date,
            policy_version_id = excluded.policy_version_id,
            indemnity = excluded.indemnity,
            interest = excluded.interest,
            deductible_applied = excluded.deductible_applied,
            category_acv = excluded.category_acv
        """,
        (
            payment.payment_id, payment.claim_id, payment.occurrence_id, payment.batch, payment.payment_date.isoformat(),
            payment.policy_version_id, fmt(payment.indemnity), fmt(payment.interest), fmt(payment.deductible_applied),
            json.dumps({k: fmt(v) for k, v in sorted(payment.category_acv.items())}),
        ),
    )


def payment_total_for_claim(conn: sqlite3.Connection, claim_id: str) -> Decimal:
    rows = conn.execute("SELECT indemnity, interest FROM payments WHERE claim_id = ?", (claim_id,)).fetchall()
    return sum((_d(r["indemnity"]) + _d(r["interest"]) for r in rows), ZERO)
PYEOF

cat > tessera/payments/scheduler.py <<'PYEOF'
"""Prompt-pay deadline and statutory interest (docs/adjudication_rules.md section 6)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable, Optional

from tessera.adjudication.rounding import ZERO, round_cents
from tessera.calendar.business_days import add_business_days, add_calendar_days
from tessera.models import Claim, PromptPayRule

DAYS_PER_YEAR = Decimal(365)


@dataclass(frozen=True)
class PromptPayOutcome:
    clock_start: Optional[date]
    deadline: Optional[date]
    days_late: int
    interest: Decimal


def clock_start_date(claim: Claim, rule: PromptPayRule) -> Optional[date]:
    if rule.clock_start == "proof_of_loss":
        return claim.proof_of_loss_date
    if rule.clock_start == "fnol":
        return claim.fnol_date
    raise ValueError(f"unknown clock_start {rule.clock_start!r} for state {rule.state}")


def payment_deadline(claim: Claim, rule: PromptPayRule, holidays: Iterable[date]) -> Optional[date]:
    start = clock_start_date(claim, rule)
    if start is None:
        return None  # the clock has not started (e.g. proof of loss not yet received)
    if rule.day_type == "business":
        return add_business_days(start, rule.deadline_days, holidays)
    if rule.day_type == "calendar":
        return add_calendar_days(start, rule.deadline_days)
    raise ValueError(f"unknown day_type {rule.day_type!r} for state {rule.state}")


def interest_amount(indemnity: Decimal, rule: PromptPayRule, days_late: int) -> Decimal:
    if not rule.interest_applies or days_late <= 0 or indemnity <= ZERO:
        return ZERO
    rate = rule.annual_rate_pct / Decimal(100)
    return round_cents(indemnity * rate * Decimal(days_late) / DAYS_PER_YEAR)


def evaluate(claim: Claim, rule: PromptPayRule, indemnity: Decimal, payment_date: date, holidays: Iterable[date]) -> PromptPayOutcome:
    start = clock_start_date(claim, rule)
    deadline = payment_deadline(claim, rule, holidays)
    if deadline is None:
        return PromptPayOutcome(start, None, 0, ZERO)
    days_late = max(0, (payment_date - deadline).days)
    return PromptPayOutcome(start, deadline, days_late, interest_amount(indemnity, rule, days_late))
PYEOF

cat > tessera/policy/coverage.py <<'PYEOF'
"""Coverage terms of a policy version: limit, deductible and category sublimits."""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from tessera.adjudication.rounding import round_cents
from tessera.models import Policy, PolicyVersion, Sublimit

PERCENTAGE_DEDUCTIBLE_PERILS = frozenset({"wind", "hail"})


def deductible_for(version: PolicyVersion, policy: Policy, peril: str) -> Decimal:
    """Occurrence deductible for a peril under a version.

    Wind and hail losses on a version that carries a wind/hail percentage
    deductible use  pct% x dwelling limit  (rounded half-up to cents); every
    other case uses the flat deductible.
    """
    if peril in PERCENTAGE_DEDUCTIBLE_PERILS and version.wind_hail_deductible_pct is not None:
        return round_cents(version.wind_hail_deductible_pct / Decimal(100) * policy.dwelling_limit)
    return round_cents(version.flat_deductible)


def sublimit_map(sublimits: Iterable[Sublimit]) -> dict[str, Decimal]:
    """{category: aggregate per-occurrence sublimit} for a version."""
    return {s.category: round_cents(s.amount) for s in sublimits}


def contents_limit(version: PolicyVersion) -> Decimal:
    return round_cents(version.contents_limit)
PYEOF

cat > tessera/policy/lookup.py <<'PYEOF'
"""Select the policy version in force for a claim.

Rule (docs/adjudication_rules.md section 1): a version is in force for a claim
when  effective_from <= loss_date < effective_to  (effective_to open-ended when
NULL).  The lookup is keyed on the *loss date*; if no version is in force the
claim has no coverage and must not be paid.
"""
from __future__ import annotations

from datetime import date
from typing import Optional, Sequence

from tessera.models import PolicyVersion


class NoCoverageInForce(Exception):
    """Raised when no policy version covers the loss date."""

    def __init__(self, policy_id: str, loss_date: date):
        super().__init__(f"no policy version of {policy_id} in force on loss date {loss_date.isoformat()}")
        self.policy_id = policy_id
        self.loss_date = loss_date


def is_in_force(version: PolicyVersion, on: date) -> bool:
    if on < version.effective_from:
        return False
    if version.effective_to is not None and on >= version.effective_to:
        return False
    return True


def find_version(versions: Sequence[PolicyVersion], loss_date: date) -> Optional[PolicyVersion]:
    """Return the version in force on *loss_date*, or None when there is none."""
    matches = [v for v in versions if is_in_force(v, loss_date)]
    if not matches:
        return None
    # Versions of one policy never overlap; if data ever did overlap, prefer the
    # most recently effective one (an endorsement supersedes its base term).
    matches.sort(key=lambda v: (v.effective_from, v.version_id))
    return matches[-1]


def select_version(versions: Sequence[PolicyVersion], policy_id: str, loss_date: date) -> PolicyVersion:
    version = find_version(versions, loss_date)
    if version is None:
        raise NoCoverageInForce(policy_id, loss_date)
    return version
PYEOF

cat > tessera/storage/db.py <<'PYEOF'
"""sqlite access layer: schema creation, deterministic loading from data/, typed readers."""
from __future__ import annotations

import csv
import json
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Optional

from tessera.models import (
    Claim,
    DepreciationRule,
    LineItem,
    Policy,
    PolicyVersion,
    PromptPayRule,
    Sublimit,
)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def _opt(value: str) -> Optional[str]:
    return value if value not in ("", None) else None


def load_data_dir(conn: sqlite3.Connection, data_dir: str | Path) -> None:
    """Populate every table from the CSV/JSON files in *data_dir* (idempotent)."""
    data_dir = Path(data_dir)
    with conn:
        for table in ("payments", "line_items", "claims", "coverage_sublimits", "policy_versions",
                      "policies", "depreciation_schedule", "prompt_pay_rules", "holidays"):
            conn.execute(f"DELETE FROM {table}")
        conn.executemany(
            "INSERT INTO policies VALUES (?,?,?,?)",
            [(r["policy_id"], r["insured"], r["state"], r["dwelling_limit"]) for r in _rows(data_dir / "policies.csv")],
        )
        conn.executemany(
            "INSERT INTO policy_versions VALUES (?,?,?,?,?,?,?)",
            [(r["version_id"], r["policy_id"], r["effective_from"], _opt(r["effective_to"]), r["contents_limit"],
              r["flat_deductible"], _opt(r["wind_hail_deductible_pct"])) for r in _rows(data_dir / "policy_versions.csv")],
        )
        conn.executemany(
            "INSERT INTO coverage_sublimits VALUES (?,?,?)",
            [(r["version_id"], r["category"], r["sublimit"]) for r in _rows(data_dir / "coverage_sublimits.csv")],
        )
        conn.executemany(
            "INSERT INTO claims VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(r["claim_id"], r["policy_id"], r["occurrence_id"], r["claim_type"], r["peril"], r["loss_date"],
              r["fnol_date"], _opt(r["proof_of_loss_date"]), r["received_date"], r["status"]) for r in _rows(data_dir / "claims.csv")],
        )
        conn.executemany(
            "INSERT INTO line_items VALUES (?,?,?,?,?,?)",
            [(r["item_id"], r["claim_id"], r["category"], r["description"], r["rcv"], r["purchase_date"])
             for r in _rows(data_dir / "line_items.csv")],
        )
        conn.executemany(
            "INSERT INTO payments VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(r["payment_id"], r["claim_id"], r["occurrence_id"], r["batch"], r["payment_date"], _opt(r["policy_version_id"]),
              r["indemnity"], r["interest"], r["deductible_applied"], r["category_acv"]) for r in _rows(data_dir / "payments_history.csv")],
        )
        conn.executemany(
            "INSERT INTO depreciation_schedule VALUES (?,?,?,?)",
            [(r["category"], r["annual_pct"], r["max_pct"], int(r["min_age_months"])) for r in _rows(data_dir / "depreciation_schedule.csv")],
        )
        rules = json.loads((data_dir / "prompt_pay_rules.json").read_text())
        conn.executemany(
            "INSERT INTO prompt_pay_rules VALUES (?,?,?,?,?,?)",
            [(state, r["clock_start"], int(r["deadline_days"]), r["day_type"], str(r["annual_rate_pct"]), 1 if r["interest_applies"] else 0)
             for state, r in sorted(rules.items())],
        )
        holidays_file = next(iter(sorted(data_dir.glob("holidays_*.csv"))), None)
        if holidays_file is not None:
            conn.executemany("INSERT INTO holidays VALUES (?,?)", [(r["date"], r["name"]) for r in _rows(holidays_file)])


# ----------------------------------------------------------------------------
# typed readers
# ----------------------------------------------------------------------------

def _d(value) -> Decimal:
    return Decimal(str(value))


def _date(value) -> Optional[date]:
    return date.fromisoformat(value) if value else None


def get_policy(conn: sqlite3.Connection, policy_id: str) -> Policy:
    r = conn.execute("SELECT * FROM policies WHERE policy_id = ?", (policy_id,)).fetchone()
    if r is None:
        raise KeyError(f"unknown policy {policy_id}")
    return Policy(r["policy_id"], r["insured"], r["state"], _d(r["dwelling_limit"]))


def get_policy_versions(conn: sqlite3.Connection, policy_id: str) -> list[PolicyVersion]:
    rows = conn.execute(
        "SELECT * FROM policy_versions WHERE policy_id = ? ORDER BY effective_from, version_id", (policy_id,)
    ).fetchall()
    return [
        PolicyVersion(
            r["version_id"], r["policy_id"], _date(r["effective_from"]), _date(r["effective_to"]),
            _d(r["contents_limit"]), _d(r["flat_deductible"]),
            _d(r["wind_hail_deductible_pct"]) if r["wind_hail_deductible_pct"] is not None else None,
        )
        for r in rows
    ]


def get_sublimits(conn: sqlite3.Connection, version_id: str) -> list[Sublimit]:
    rows = conn.execute(
        "SELECT * FROM coverage_sublimits WHERE version_id = ? ORDER BY category", (version_id,)
    ).fetchall()
    return [Sublimit(r["version_id"], r["category"], _d(r["sublimit"])) for r in rows]


def _claim(r: sqlite3.Row) -> Claim:
    return Claim(
        r["claim_id"], r["policy_id"], r["occurrence_id"], r["claim_type"], r["peril"], _date(r["loss_date"]),
        _date(r["fnol_date"]), _date(r["proof_of_loss_date"]), _date(r["received_date"]), r["status"],
    )


def get_claims_for_batch(conn: sqlite3.Connection, batch: str) -> list[Claim]:
    """All claims received in the batch month, in deterministic processing order."""
    rows = conn.execute(
        "SELECT * FROM claims WHERE substr(received_date, 1, 7) = ? ORDER BY loss_date, received_date, claim_id",
        (batch,),
    ).fetchall()
    return [_claim(r) for r in rows]


def get_line_items(conn: sqlite3.Connection, claim_id: str) -> list[LineItem]:
    rows = conn.execute("SELECT * FROM line_items WHERE claim_id = ? ORDER BY item_id", (claim_id,)).fetchall()
    return [LineItem(r["item_id"], r["claim_id"], r["category"], r["description"], _d(r["rcv"]), _date(r["purchase_date"])) for r in rows]


def get_depreciation_schedule(conn: sqlite3.Connection) -> dict[str, DepreciationRule]:
    rows = conn.execute("SELECT * FROM depreciation_schedule").fetchall()
    return {r["category"]: DepreciationRule(r["category"], _d(r["annual_pct"]), _d(r["max_pct"]), int(r["min_age_months"])) for r in rows}


def get_prompt_pay_rules(conn: sqlite3.Connection) -> dict[str, PromptPayRule]:
    rows = conn.execute("SELECT * FROM prompt_pay_rules").fetchall()
    return {
        r["state"]: PromptPayRule(r["state"], r["clock_start"], int(r["deadline_days"]), r["day_type"], _d(r["annual_rate_pct"]), bool(r["interest_applies"]))
        for r in rows
    }


def get_holidays(conn: sqlite3.Connection) -> set[date]:
    return {date.fromisoformat(r["day"]) for r in conn.execute("SELECT day FROM holidays").fetchall()}


def iter_tables(conn: sqlite3.Connection) -> Iterable[str]:
    for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"):
        yield r["name"]
PYEOF

cat > tessera/valuation/depreciation.py <<'PYEOF'
"""Actual cash value (ACV) of a line item from its replacement cost (RCV).

docs/adjudication_rules.md section 3:
  * age is counted in whole calendar months between purchase and loss date
    (day-of-month aware);
  * no depreciation while age < min_age_months for the category;
  * depreciation % = min(max_pct, annual_pct x months / 12);
  * ACV = RCV x (100 - depreciation %) / 100, rounded half-up to cents.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from tessera.adjudication.rounding import round_cents
from tessera.models import DepreciationRule, LineItem, LineValue


def whole_months_between(start: date, end: date) -> int:
    """Completed calendar months from *start* to *end* (0 if end precedes start)."""
    if end < start:
        return 0
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return months


def depreciation_pct(rule: DepreciationRule, age_months: int) -> Decimal:
    if age_months < rule.min_age_months:
        return Decimal(0)
    accrued = rule.annual_pct * Decimal(age_months) / Decimal(12)
    return min(rule.max_pct, accrued)


def value_item(item: LineItem, loss_date: date, schedule: dict[str, DepreciationRule]) -> LineValue:
    try:
        rule = schedule[item.category]
    except KeyError as exc:
        raise KeyError(f"no depreciation rule for category {item.category!r} (item {item.item_id})") from exc
    age = whole_months_between(item.purchase_date, loss_date)
    pct = depreciation_pct(rule, age)
    acv = round_cents(item.rcv * (Decimal(100) - pct) / Decimal(100))
    return LineValue(item=item, age_months=age, depreciation_pct=pct, acv=acv)
PYEOF

find /app -name __pycache__ -type d -prune -exec rm -rf {} +
python -m tessera.cli build-db --data data --out data/claims.db
echo "fix applied: $(printf '%s ' tessera/adjudication/engine.py tessera/adjudication/rounding.py tessera/calendar/business_days.py tessera/models.py tessera/payments/ledger.py tessera/payments/scheduler.py tessera/policy/coverage.py tessera/policy/lookup.py tessera/storage/db.py tessera/valuation/depreciation.py)"
