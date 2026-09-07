"""Full Nordwind August statement through the documented CLI: performance, correctness, persistence."""
from __future__ import annotations

from collections import Counter


from conftest import (
    FULL_RUN_BUDGET,
    FULL_STATEMENT,
    SQL_CONNECTION_BUDGET,
    SQL_STATEMENT_BUDGET,
    db_query,
    german_to_cents,
    load_gt,
    require_finished,
    statement_lines,
)

GT = load_gt("ground_truth_full.json")
RULES = {"A1", "A2", "B1", "B2", "B3"}
REASONS = {"DEBIT", "INVOICE_CONSUMED", "NO_CANDIDATE"}


def _diff(got: dict, expected: dict, limit: int = 8) -> str:
    bad = [(k, expected[k], got.get(k)) for k in expected if got.get(k) != expected[k]]
    extra = sorted(set(got) - set(expected))
    msg = f"{len(bad)} of {len(expected)} lines differ from the spec-derived expectation"
    for k, e, g in bad[:limit]:
        msg += f"\n  {k}: expected {e}, got {g}"
    if extra:
        msg += f"\n  unexpected line ids in reports: {extra[:5]}"
    return msg


def _expect_tag(run, tag: str) -> None:
    got = run.outcomes()
    ids = GT["tags"][tag]
    assert ids, f"fixture has no lines tagged {tag}"
    exp = {lid: GT["lines"][lid] for lid in ids}
    sub = {lid: got.get(lid) for lid in ids}
    assert sub == exp, _diff(sub, exp)


# --------------------------------------------------------------------------- #
# performance
# --------------------------------------------------------------------------- #
def test_full_run_completes_within_budget(full_run):
    require_finished(full_run, "full statement run")
    assert full_run.elapsed <= FULL_RUN_BUDGET, (
        f"full statement took {full_run.elapsed:.1f}s, budget is {FULL_RUN_BUDGET:.0f}s"
    )


def test_sql_statement_budget(full_run):
    require_finished(full_run, "full statement run")
    assert full_run.sql_statements is not None, "no SQLite trace was recorded for the run"
    assert full_run.sql_statements <= SQL_STATEMENT_BUDGET, (
        f"{full_run.sql_statements} SQLite statements executed for 12,000 lines "
        f"(budget {SQL_STATEMENT_BUDGET}); the ledger is still being queried per candidate"
    )


def test_sql_connection_budget(full_run):
    require_finished(full_run, "full statement run")
    assert full_run.sql_connects is not None, "no SQLite trace was recorded for the run"
    assert full_run.sql_connects <= SQL_CONNECTION_BUDGET, (
        f"{full_run.sql_connects} SQLite connections opened for 12,000 lines (budget {SQL_CONNECTION_BUDGET}); "
        f"the ledger is still being opened per line or per invoice"
    )


# --------------------------------------------------------------------------- #
# report contract
# --------------------------------------------------------------------------- #
def test_report_files_and_columns(full_run):
    require_finished(full_run, "full statement run")
    out = full_run.out_dir
    for name in ("matches.csv", "unmatched.csv", "summary.json"):
        assert (out / name).is_file(), f"{name} missing"
    assert (out / "matches.csv").read_text(encoding="utf-8").splitlines()[0] == "line_id,booking_date,amount,rule,invoice_ids"
    assert (out / "unmatched.csv").read_text(encoding="utf-8").splitlines()[0] == "line_id,booking_date,amount,reason"

    stmt = statement_lines(FULL_STATEMENT)
    matches, unmatched = full_run.matches(), full_run.unmatched()
    assert set(matches) | set(unmatched) == set(stmt)
    assert not (set(matches) & set(unmatched)), "a line appears in both reports"
    for lid, row in list(matches.items()) + list(unmatched.items()):
        src = stmt[lid]
        d, m, y = src["Buchungstag"].split(".")
        assert row["booking_date"] == f"{y}-{m}-{d}"
        whole, _, frac = row["amount"].partition(".")
        cents = (int(whole.lstrip("-")) * 100 + int(frac.ljust(2, "0"))) * (-1 if whole.startswith("-") else 1)
        assert cents == german_to_cents(src["Betrag"]), f"{lid}: amount {row['amount']} vs {src['Betrag']}"
    for row in matches.values():
        assert row["rule"] in RULES
        ids = [int(x) for x in row["invoice_ids"].split("|")]
        assert ids == sorted(ids) and len(set(ids)) == len(ids)
    for row in unmatched.values():
        assert row["reason"] in REASONS


# --------------------------------------------------------------------------- #
# matching correctness against the spec oracle
# --------------------------------------------------------------------------- #
def test_every_line_matches_ground_truth(full_run):
    require_finished(full_run, "full statement run")
    got = full_run.outcomes()
    assert got == GT["lines"], _diff(got, GT["lines"])


def test_large_customer_batch_payments_matched(full_run):
    """Rule B3 for customers with more than 12 open invoices (the PR-418 cap victims)."""
    require_finished(full_run, "full statement run")
    got = full_run.outcomes()
    ids = GT["large_customer_batches"]
    assert len(ids) == 17
    bad = {lid: got.get(lid) for lid in ids if got.get(lid) != GT["lines"][lid]}
    assert not bad, f"{len(bad)} of 17 large-customer batch payments wrong: {list(bad.items())[:5]}"
    assert all(len(GT["lines"][lid]["invoice_ids"]) >= 3 for lid in ids)


def test_fuzzy_reference_with_unknown_iban(full_run):
    require_finished(full_run, "full statement run")
    _expect_tag(full_run, "a2_unknown_iban")


def test_processing_order_is_booking_date_then_line_id(full_run):
    """Late-booked lines appended to the export must be processed by booking date."""
    require_finished(full_run, "full statement run")
    _expect_tag(full_run, "order_conflict")


def test_batch_window_and_b2_window_are_enforced(full_run):
    require_finished(full_run, "full statement run")
    _expect_tag(full_run, "b3_window_trap")
    _expect_tag(full_run, "b2_window_trap")
    got = full_run.outcomes()
    for tag in ("b3_window_trap", "b2_window_trap"):
        for lid in GT["tags"][tag]:
            assert got[lid] == {"reason": "NO_CANDIDATE"}


def test_unmatched_reason_codes(full_run):
    require_finished(full_run, "full statement run")
    got = full_run.outcomes()
    for lid in GT["tags"]["debit"]:
        assert got[lid] == {"reason": "DEBIT"}
    for lid in GT["tags"]["duplicate_payment"]:
        assert got[lid] == {"reason": "INVOICE_CONSUMED"}, lid
    for lid in GT["tags"]["ambiguous_name"]:
        assert got[lid] == {"reason": "NO_CANDIDATE"}, lid


def test_one_invoice_one_match(full_run):
    require_finished(full_run, "full statement run")
    counts = Counter(i for row in full_run.matches().values() for i in row["invoice_ids"].split("|"))
    dup = {k: v for k, v in counts.items() if v > 1}
    assert not dup, f"invoices matched more than once: {list(dup.items())[:5]}"


def test_summary_is_consistent(full_run):
    require_finished(full_run, "full statement run")
    s = full_run.summary()
    matches, unmatched = full_run.matches(), full_run.unmatched()
    assert s["lines"] == 12000
    assert s["matched_lines"] == len(matches)
    assert s["unmatched_lines"] == len(unmatched)
    assert s["matched_invoices"] == sum(len(r["invoice_ids"].split("|")) for r in matches.values())
    by_rule = Counter(r["rule"] for r in matches.values())
    assert {k: v for k, v in s["by_rule"].items() if v} == dict(by_rule)
    by_reason = Counter(r["reason"] for r in unmatched.values())
    assert {k: v for k, v in s["unmatched_by_reason"].items() if v} == dict(by_reason)
    total = 0
    for r in matches.values():
        whole, _, frac = r["amount"].partition(".")
        total += int(whole) * 100 + int(frac.ljust(2, "0"))
    assert s["matched_amount_cents"] == total
    exp = GT["summary"]
    assert (s["matched_lines"], s["unmatched_lines"], s["matched_invoices"], s["matched_amount_cents"]) == (
        exp["matched_lines"], exp["unmatched_lines"], exp["matched_invoices"], exp["matched_amount_cents"])


# --------------------------------------------------------------------------- #
# persistence contract
# --------------------------------------------------------------------------- #
def test_db_match_results_mirror_report(full_run):
    require_finished(full_run, "full statement run")
    rows = db_query(full_run.db_path, "SELECT line_id, invoice_id, rule, amount_cents FROM match_results")
    got = {(lid, int(iid)): (rule, int(cents)) for lid, iid, rule, cents in rows}
    exp = {}
    for lid, r in full_run.matches().items():
        whole, _, frac = r["amount"].partition(".")
        cents = int(whole) * 100 + int(frac.ljust(2, "0"))
        for iid in r["invoice_ids"].split("|"):
            exp[(lid, int(iid))] = (r["rule"], cents)
    assert got == exp


def test_db_invoice_status_reflects_matches(full_run):
    require_finished(full_run, "full statement run")
    before = dict(db_query(full_run.baseline_db, "SELECT id, status FROM invoices"))
    after = dict(db_query(full_run.db_path, "SELECT id, status FROM invoices"))
    assert set(before) == set(after), "invoice rows were added or removed"
    matched = {int(i) for r in full_run.matches().values() for i in r["invoice_ids"].split("|")}
    assert all(before[i] == "open" for i in matched), "a matched invoice was not open in the ledger"
    for iid, status in after.items():
        if iid in matched:
            assert status == "paid", f"invoice {iid} matched but status {status}"
        else:
            assert status == before[iid], f"invoice {iid} status changed without a match"


def test_db_bank_lines_persisted(full_run):
    require_finished(full_run, "full statement run")
    cols = {r[1] for r in db_query(full_run.db_path, "PRAGMA table_info(bank_lines)")}
    assert {"line_id", "booking_date", "amount_cents"} <= cols
    rows = db_query(full_run.db_path, "SELECT line_id, amount_cents FROM bank_lines")
    stmt = statement_lines(FULL_STATEMENT)
    assert {r[0] for r in rows} == set(stmt)
    assert all(int(c) == german_to_cents(stmt[lid]["Betrag"]) for lid, c in rows)


def test_original_schema_columns_preserved(full_run):
    require_finished(full_run, "full statement run")
    expected = {
        "invoices": {"id", "customer_id", "reference", "amount_cents", "currency", "due_date", "status"},
        "match_results": {"line_id", "invoice_id", "rule", "amount_cents"},
        "customers": {"customer_id", "legal_name"},
    }
    for table, cols in expected.items():
        have = {r[1] for r in db_query(full_run.db_path, f"PRAGMA table_info({table})")}
        assert cols <= have, f"{table} lost columns {cols - have}"


# --------------------------------------------------------------------------- #
# determinism and re-runs
# --------------------------------------------------------------------------- #
def test_repeated_run_is_byte_identical(full_run, full_rerun_fresh):
    require_finished(full_rerun_fresh, "second full statement run")
    for name in ("matches.csv", "unmatched.csv", "summary.json"):
        a = (full_run.out_dir / name).read_bytes()
        b = (full_rerun_fresh.out_dir / name).read_bytes()
        assert a == b, f"{name} differs between two runs on identical inputs"


def test_rerun_on_reconciled_ledger(full_run, full_rerun_same_db):
    """Startup on the already-migrated, already-reconciled ledger must work and honour paid invoices."""
    require_finished(full_rerun_same_db, "rerun on reconciled ledger")
    exp = GT["rerun_on_same_db"]
    s = full_rerun_same_db.summary()
    assert s["matched_lines"] == exp["matched_lines"]
    assert s["matched_invoices"] == exp["matched_invoices"]
    assert {k: v for k, v in s["by_rule"].items() if v} == exp["by_rule"]
    assert {k: v for k, v in s["unmatched_by_reason"].items() if v} == exp["unmatched_by_reason"]
    n_rows = db_query(full_run.db_path, "SELECT COUNT(*) FROM match_results")[0][0]
    assert n_rows == GT["summary"]["matched_invoices"] + exp["matched_invoices"]
    paid = db_query(full_run.db_path, "SELECT COUNT(*) FROM invoices WHERE status = 'paid'")[0][0]
    paid_before = db_query(full_run.baseline_db, "SELECT COUNT(*) FROM invoices WHERE status = 'paid'")[0][0]
    assert paid == paid_before + GT["summary"]["matched_invoices"] + exp["matched_invoices"]
