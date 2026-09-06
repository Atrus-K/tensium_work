"""The seven claims sampled by AUD-2024-117 must match the auditor's recomputation cents-exact."""
from __future__ import annotations

import csv
from decimal import Decimal

import pytest

from conftest import APP_DIR, D

EXPECTED = APP_DIR / "docs" / "tickets" / "AUD-2024-117_expected.csv"


def _expected_rows():
    with EXPECTED.open(newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.mark.parametrize("exp", _expected_rows(), ids=lambda r: r["claim_id"])
def test_sampled_claim_matches_auditor(main_run, exp):
    row = main_run.rows[exp["claim_id"]]
    assert row["policy_version_id"] == exp["policy_version_id"]
    assert row["status"] == exp["status"]
    for f in ("gross_acv", "sublimit_reduction", "deductible_applied", "indemnity", "interest"):
        assert D(row[f]) == D(exp[f]), f"{exp['claim_id']} {f}: engine={row[f]} auditor={exp[f]}"
    assert int(row["days_late"]) == int(exp["days_late"])
