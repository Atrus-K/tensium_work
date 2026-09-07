"""A second statement (September, different composition) against the same ledger."""
from __future__ import annotations

from collections import Counter

from conftest import ALT_STATEMENT, db_query, load_gt, require_finished, statement_lines

GT = load_gt("ground_truth_alt.json")


def test_alt_statement_completes(alt_run):
    require_finished(alt_run, "alternative statement run")
    assert alt_run.elapsed <= 60.0, f"1,500-line statement took {alt_run.elapsed:.1f}s"


def test_alt_statement_matches_ground_truth(alt_run):
    require_finished(alt_run, "alternative statement run")
    got = alt_run.outcomes()
    assert set(got) == set(statement_lines(ALT_STATEMENT))
    bad = [(k, GT["lines"][k], got.get(k)) for k in GT["lines"] if got.get(k) != GT["lines"][k]]
    assert not bad, f"{len(bad)} of {len(GT['lines'])} lines differ: {bad[:8]}"


def test_alt_statement_special_scenarios(alt_run):
    require_finished(alt_run, "alternative statement run")
    got = alt_run.outcomes()
    for tag in ("b3_large", "order_conflict", "a2_unknown_iban", "b3_window_trap", "duplicate_payment"):
        ids = GT["tags"][tag]
        assert ids, tag
        bad = {lid: got.get(lid) for lid in ids if got.get(lid) != GT["lines"][lid]}
        assert not bad, f"{tag}: {bad}"
    assert len(GT["large_customer_batches"]) >= 5
    assert all(got[lid]["rule"] == "B3" for lid in GT["large_customer_batches"])


def test_alt_statement_summary_and_db(alt_run):
    require_finished(alt_run, "alternative statement run")
    s = alt_run.summary()
    exp = GT["summary"]
    assert s["lines"] == exp["lines"] == 1500
    assert s["matched_lines"] == exp["matched_lines"]
    assert s["matched_invoices"] == exp["matched_invoices"]
    assert s["matched_amount_cents"] == exp["matched_amount_cents"]
    assert {k: v for k, v in s["by_rule"].items() if v} == exp["by_rule"]
    assert {k: v for k, v in s["unmatched_by_reason"].items() if v} == exp["unmatched_by_reason"]

    counts = Counter(i for row in alt_run.matches().values() for i in row["invoice_ids"].split("|"))
    assert not [k for k, v in counts.items() if v > 1]
    rows = db_query(alt_run.db_path, "SELECT line_id, invoice_id, rule FROM match_results")
    got = {(lid, int(iid)): rule for lid, iid, rule in rows}
    exp_rows = {(lid, int(i)): r["rule"] for lid, r in alt_run.matches().items() for i in r["invoice_ids"].split("|")}
    assert got == exp_rows
    paid = {r[0] for r in db_query(alt_run.db_path, "SELECT id FROM invoices WHERE status = 'paid'")}
    assert {iid for _, iid in exp_rows} <= paid
    assert db_query(alt_run.db_path, "SELECT COUNT(*) FROM bank_lines")[0][0] == 1500
