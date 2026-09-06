"""Payment ledger: prior activity on a claim and idempotent payment writes."""
from __future__ import annotations

import json
import sqlite3
from datetime import date

from tessera.adjudication.rounding import fmt, round_cents
from tessera.models import AdjudicationResult, Payment, PriorActivity


def prior_activity(conn: sqlite3.Connection, claim_id: str, batch: str) -> PriorActivity:
    """Indemnity and deductible already recorded against *claim_id* in earlier batches."""
    prior = PriorActivity()
    rows = conn.execute(
        "SELECT indemnity, deductible_applied FROM payments WHERE claim_id = ? AND batch <> ? ORDER BY payment_id",
        (claim_id, batch),
    ).fetchall()
    for r in rows:
        prior.indemnity_paid += float(r["indemnity"])
        prior.deductible_absorbed += float(r["deductible_applied"])
    return prior


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
    """Insert or replace the payment for (claim_id, batch)."""
    conn.execute(
        """
        INSERT OR REPLACE INTO payments (payment_id, claim_id, occurrence_id, batch, payment_date, policy_version_id,
                                         indemnity, interest, deductible_applied, category_acv)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            payment.payment_id, payment.claim_id, payment.occurrence_id, payment.batch, payment.payment_date.isoformat(),
            payment.policy_version_id, fmt(payment.indemnity), fmt(payment.interest), fmt(payment.deductible_applied),
            json.dumps({k: fmt(v) for k, v in sorted(payment.category_acv.items())}),
        ),
    )


def payment_total_for_claim(conn: sqlite3.Connection, claim_id: str) -> float:
    rows = conn.execute("SELECT indemnity, interest FROM payments WHERE claim_id = ?", (claim_id,)).fetchall()
    return sum(float(r["indemnity"]) + float(r["interest"]) for r in rows)
