"""Smaller CLI contracts: the 200-line sample, migrations, `lookup`, error exits, visible unit tests."""
from __future__ import annotations

import subprocess
import sys

from conftest import (
    APP,
    DATA,
    SAMPLE_STATEMENT,
    SMALL_RUN_TIMEOUT,
    db_query,
    fresh_db,
    load_gt,
    require_finished,
    require_full_ok,
    run_cli,
    run_statement,
)

GT_SAMPLE = load_gt("ground_truth_sample200.json")


def test_sample_200_matches_ground_truth(sample_run):
    require_finished(sample_run, "sample_200 run")
    got = sample_run.outcomes()
    bad = [(k, GT_SAMPLE["lines"][k], got.get(k)) for k in GT_SAMPLE["lines"] if got.get(k) != GT_SAMPLE["lines"][k]]
    assert len(got) == 200
    assert not bad, f"{len(bad)} of 200 lines differ: {bad[:8]}"
    s = sample_run.summary()
    assert s["matched_lines"] == GT_SAMPLE["summary"]["matched_lines"]
    assert s["matched_amount_cents"] == GT_SAMPLE["summary"]["matched_amount_cents"]


def test_migrate_is_idempotent_and_run_works_afterwards(workspace, full_run):
    require_full_ok()
    db = fresh_db(workspace, "migrate")
    first = run_cli(["migrate", "--db", str(db)], timeout=SMALL_RUN_TIMEOUT)
    assert first.exit_code == 0, first.stderr
    second = run_cli(["migrate", "--db", str(db)], timeout=SMALL_RUN_TIMEOUT)
    assert second.exit_code == 0, second.stderr
    # ledger content untouched by migrations
    assert db_query(db, "SELECT COUNT(*) FROM invoices")[0][0] == db_query(DATA / "recon.db", "SELECT COUNT(*) FROM invoices")[0][0]
    assert db_query(db, "SELECT COUNT(*) FROM invoices WHERE status='open'")[0][0] == db_query(
        DATA / "recon.db", "SELECT COUNT(*) FROM invoices WHERE status='open'")[0][0]
    res = run_statement(workspace, "after_migrate", SAMPLE_STATEMENT, timeout=SMALL_RUN_TIMEOUT, db=db)
    require_finished(res, "run on pre-migrated ledger")
    assert res.summary()["matched_lines"] == GT_SAMPLE["summary"]["matched_lines"]


def _pick_invoice(where: str) -> tuple[int, str]:
    rows = db_query(DATA / "recon.db", f"SELECT id, reference FROM invoices WHERE {where} ORDER BY id LIMIT 1")
    assert rows, where
    return int(rows[0][0]), rows[0][1]


def test_lookup_accepts_any_formatting_variant(workspace):
    db = fresh_db(workspace, "lookup")
    # ledger row stored canonically, queried with slash / unpadded / lower-case variants
    iid, ref = _pick_invoice("reference GLOB 'RE-2026-[0-9][0-9][0-9][0-9][0-9][0-9]' AND id > 1000")
    seq = int(ref.split("-")[-1])
    for query in (f"re 2026/{seq:06d}", f"RE-2026-{seq}", f"RE2026-{seq:06d}", ref):
        res = run_cli(["lookup", "--db", str(db), "--reference", query], timeout=SMALL_RUN_TIMEOUT)
        assert res.exit_code == 0, f"lookup {query!r}: exit {res.exit_code} {res.stderr}"
        ids = [int(line.split("\t")[0]) for line in res.stdout.strip().splitlines()]
        assert ids == [iid], f"lookup {query!r} returned {ids}, expected [{iid}]"
    # ledger row stored with a slash, queried canonically
    iid2, ref2 = _pick_invoice("reference LIKE 'RE-2026/%'")
    seq2 = int(ref2.split("/")[-1])
    res = run_cli(["lookup", "--db", str(db), "--reference", f"RE-2026-{seq2:06d}"], timeout=SMALL_RUN_TIMEOUT)
    assert res.exit_code == 0, res.stderr
    assert [int(l.split("\t")[0]) for l in res.stdout.strip().splitlines()] == [iid2]
    # ledger row stored unpadded, queried padded
    iid3, ref3 = _pick_invoice("reference GLOB 'RE-2026-[1-9]*' AND length(reference) < 14")
    seq3 = int(ref3.split("-")[-1])
    res = run_cli(["lookup", "--db", str(db), "--reference", f"RE-2026-{seq3:06d}"], timeout=SMALL_RUN_TIMEOUT)
    assert res.exit_code == 0, res.stderr
    assert [int(l.split("\t")[0]) for l in res.stdout.strip().splitlines()] == [iid3]


def test_lookup_unknown_reference_exits_1(workspace):
    db = fresh_db(workspace, "lookup_unknown")
    res = run_cli(["lookup", "--db", str(db), "--reference", "RE-2026-999999"], timeout=SMALL_RUN_TIMEOUT)
    assert res.exit_code == 1
    assert res.stdout.strip() == ""


def test_missing_input_file_exits_2(workspace):
    db = fresh_db(workspace, "missing")
    res = run_cli(
        ["run", "--db", str(db), "--statement", str(workspace / "does_not_exist.csv"),
         "--customers", str(DATA / "customers.csv"), "--out", str(workspace / "missing_out")],
        timeout=SMALL_RUN_TIMEOUT,
    )
    assert res.exit_code == 2


def test_visible_unit_suite_still_passes():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests_unit", "-q", "-p", "no:cacheprovider"],
        cwd=str(APP), capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]
    assert " passed" in proc.stdout
