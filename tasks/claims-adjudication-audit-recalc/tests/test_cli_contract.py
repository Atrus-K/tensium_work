"""The CLI / export / ledger contract stated in the brief."""
from __future__ import annotations

import sqlite3
from decimal import Decimal

from conftest import EXPORT_COLUMNS, D


def test_export_has_exact_column_set(main_run):
    assert main_run.columns == EXPORT_COLUMNS


def test_export_has_one_row_per_batch_claim(main_run):
    assert sorted(main_run.rows) == sorted(main_run.batch_claim_ids())
    assert len(main_run.rows) == 30


def test_build_db_creates_payments_table_with_history(main_run):
    conn = sqlite3.connect(str(main_run.db_path))
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"payments", "claims", "policy_versions", "line_items"} <= tables
        hist = conn.execute("SELECT COUNT(*) FROM payments WHERE batch <> ?", (main_run.batch,)).fetchone()[0]
    finally:
        conn.close()
    assert hist == 3  # payments_history.csv rows survive the batch run untouched


def test_payment_total_is_indemnity_plus_interest(any_run):
    for cid, row in any_run.rows.items():
        assert D(row["payment_total"]) == D(row["indemnity"]) + D(row["interest"]), cid


def test_export_payment_matches_ledger_row(any_run):
    for cid, row in any_run.rows.items():
        pays = any_run.payments_for_claim(cid)
        if row["status"] == "no_coverage":
            continue
        assert len(pays) == 1, f"{cid}: expected exactly one payment row for the batch"
        p = pays[0]
        assert p["batch"] == any_run.batch
        assert p["payment_date"] == any_run.as_of.isoformat()
        assert D(p["indemnity"]) == D(row["indemnity"]), cid
        assert D(p["interest"]) == D(row["interest"]), cid
        assert D(p["deductible_applied"]) == D(row["deductible_applied"]), cid
        assert (p["policy_version_id"] or "") == row["policy_version_id"], cid
