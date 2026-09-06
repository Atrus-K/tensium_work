"""Auditor CSV export of a batch run."""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from tessera.adjudication.rounding import fmt
from tessera.models import AdjudicationResult
from tessera.storage import db

COLUMNS = [
    "claim_id",
    "occurrence_id",
    "policy_id",
    "state",
    "policy_version_id",
    "status",
    "gross_acv",
    "sublimit_reduction",
    "deductible_applied",
    "indemnity",
    "days_late",
    "interest",
    "payment_total",
]


def result_row(conn: sqlite3.Connection, result: AdjudicationResult) -> dict[str, str]:
    policy = db.get_policy(conn, result.claim.policy_id)
    return {
        "claim_id": result.claim.claim_id,
        "occurrence_id": result.claim.occurrence_id,
        "policy_id": policy.policy_id,
        "state": policy.state,
        "policy_version_id": result.policy_version_id or "",
        "status": result.status,
        "gross_acv": fmt(result.gross_acv),
        "sublimit_reduction": fmt(result.sublimit_reduction),
        "deductible_applied": fmt(result.deductible_applied),
        "indemnity": fmt(result.indemnity),
        "days_late": str(result.days_late),
        "interest": fmt(result.interest),
        "payment_total": fmt(result.payment_total),
    }


def write_export(conn: sqlite3.Connection, results: list[AdjudicationResult], out_path: str | Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted((result_row(conn, r) for r in results), key=lambda r: r["claim_id"])
    with out_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return out_path
