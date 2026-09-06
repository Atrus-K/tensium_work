"""Core adjudication of one claim.

For each claim: value the line items, apply category sublimits, subtract the
deductible, cap at the Coverage C limit, then compute prompt-pay interest.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import date

from tessera.adjudication.rounding import clamp_non_negative, round_cents
from tessera.models import AdjudicationResult, Claim, LineValue, PromptPayRule
from tessera.payments import ledger, scheduler
from tessera.policy import coverage, lookup
from tessera.storage import db
from tessera.valuation.depreciation import value_item

log = logging.getLogger("tessera.engine")


class Adjudicator:
    """Holds the reference tables for a batch run and adjudicates claims one at a time."""

    def __init__(self, conn: sqlite3.Connection, batch: str, payment_date: date):
        self.conn = conn
        self.batch = batch
        self.payment_date = payment_date
        self.schedule = db.get_depreciation_schedule(conn)
        self.prompt_pay_rules = db.get_prompt_pay_rules(conn)

    # ------------------------------------------------------------------ steps
    def value_lines(self, claim: Claim) -> list[LineValue]:
        return [value_item(item, claim.loss_date, self.schedule) for item in db.get_line_items(self.conn, claim.claim_id)]

    @staticmethod
    def apply_sublimits(lines: list[LineValue], sublimits: dict[str, float]) -> tuple[dict[str, float], float]:
        """Cap each line at its category sublimit; return per-category totals and the total reduction."""
        covered: dict[str, float] = {}
        reduction = 0.0
        for lv in lines:
            cap = sublimits.get(lv.item.category)
            amount = lv.acv if cap is None else min(lv.acv, cap)
            reduction += lv.acv - amount
            covered[lv.item.category] = covered.get(lv.item.category, 0.0) + amount
        return covered, reduction

    def prompt_pay_rule(self, state: str) -> PromptPayRule:
        try:
            return self.prompt_pay_rules[state]
        except KeyError as exc:
            raise KeyError(f"no prompt-pay rule configured for state {state!r}") from exc

    # ------------------------------------------------------------------ main
    def adjudicate(self, claim: Claim) -> AdjudicationResult:
        policy = db.get_policy(self.conn, claim.policy_id)
        versions = db.get_policy_versions(self.conn, claim.policy_id)
        version = lookup.select_version(versions, claim.policy_id, claim.received_date)

        lines = self.value_lines(claim)
        gross = sum(lv.acv for lv in lines)

        sublimits = coverage.sublimit_map(db.get_sublimits(self.conn, version.version_id))
        covered_by_category, sublimit_reduction = self.apply_sublimits(lines, sublimits)
        covered = sum(covered_by_category.values())

        prior = ledger.prior_activity(self.conn, claim.claim_id, self.batch)
        deductible = coverage.deductible_for(version)
        deductible_remaining = clamp_non_negative(deductible - prior.deductible_absorbed)
        deductible_applied = min(deductible_remaining, covered)

        limit_headroom = clamp_non_negative(coverage.contents_limit(version) - prior.indemnity_paid)
        indemnity = round_cents(min(covered - deductible_applied, limit_headroom))

        rule = self.prompt_pay_rule(policy.state)
        outcome = scheduler.evaluate(claim, rule, indemnity, self.payment_date)

        status = "paid" if indemnity > 0 else "zero_payment"
        log.info(
            "%s: version=%s gross=%.2f sublimit_reduction=%.2f deductible=%.2f applied=%.2f indemnity=%.2f interest=%.2f (%d days late, deadline %s)",
            claim.claim_id, version.version_id, gross, sublimit_reduction, deductible, deductible_applied, indemnity,
            outcome.interest, outcome.days_late, outcome.deadline.isoformat(),
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
            category_acv={k: round_cents(v) for k, v in covered_by_category.items()},
            line_values=lines,
        )


def run_batch(conn: sqlite3.Connection, batch: str, as_of: date) -> list[AdjudicationResult]:
    """Adjudicate every claim of *batch* and record the payments."""
    adjudicator = Adjudicator(conn, batch, payment_date=as_of)
    results: list[AdjudicationResult] = []
    with conn:
        for claim in db.get_claims_for_batch(conn, batch):
            result = adjudicator.adjudicate(claim)
            results.append(result)
            ledger.record_payment(conn, ledger.build_payment(result, batch, as_of))
    return results
