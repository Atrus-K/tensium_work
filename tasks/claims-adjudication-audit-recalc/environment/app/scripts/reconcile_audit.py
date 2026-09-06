#!/usr/bin/env python3
"""Re-run the June 2024 batch into a scratch database and diff the export
against the auditor's recomputed figures (docs/tickets/AUD-2024-117_expected.csv).

Usage: python scripts/reconcile_audit.py [--keep]

Only the seven claims the auditor sampled are compared here; a clean diff on
those does not prove the rest of the batch is right.
"""
from __future__ import annotations

import argparse
import csv
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tessera.cli import main as tessera_main  # noqa: E402

EXPECTED = ROOT / "docs" / "tickets" / "AUD-2024-117_expected.csv"
COMPARE = ("policy_version_id", "status", "gross_acv", "sublimit_reduction", "deductible_applied", "indemnity", "days_late", "interest")


def load(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="") as fh:
        return {row["claim_id"]: row for row in csv.DictReader(fh)}


def same(field: str, a: str, b: str) -> bool:
    if field in ("policy_version_id", "status"):
        return a.strip() == b.strip()
    return Decimal(a or "0") == Decimal(b or "0")


def run() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="keep the scratch database/export and print their paths")
    opts = ap.parse_args()

    work = Path(tempfile.mkdtemp(prefix="tessera-reconcile-"))
    db_path = work / "claims.db"
    export = work / "audit_2024-06.csv"
    tessera_main(["build-db", "--data", str(ROOT / "data"), "--out", str(db_path)])
    tessera_main(["adjudicate", "--db", str(db_path), "--as-of", "2024-06-30", "--batch", "2024-06", "--out", str(export)])

    got = load(export)
    want = load(EXPECTED)
    mismatches = 0
    for claim_id, exp in sorted(want.items()):
        row = got.get(claim_id)
        if row is None:
            print(f"{claim_id}: MISSING from export")
            mismatches += 1
            continue
        diffs = [f"{f}: engine={row[f]!r} auditor={exp[f]!r}" for f in COMPARE if not same(f, row[f], exp[f])]
        if diffs:
            mismatches += 1
            print(f"{claim_id}: MISMATCH")
            for d in diffs:
                print(f"    {d}")
        else:
            print(f"{claim_id}: ok")
    print(f"\n{len(want) - mismatches}/{len(want)} sampled claims reconcile")
    if opts.keep:
        print(f"scratch files kept in {work}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(run())
