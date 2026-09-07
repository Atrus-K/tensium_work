"""Smaller CLI contracts: the 200-line sample, migrations, `lookup`, error exits, visible unit tests."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from conftest import (
    APP,
    DATA,
    SAMPLE_STATEMENT,
    SMALL_RUN_TIMEOUT,
    baseline_db,
    build_v1_ledger,
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
    base = baseline_db(workspace)
    assert db_query(db, "SELECT COUNT(*) FROM invoices")[0][0] == db_query(base, "SELECT COUNT(*) FROM invoices")[0][0]
    assert db_query(db, "SELECT COUNT(*) FROM invoices WHERE status='open'")[0][0] == db_query(
        base, "SELECT COUNT(*) FROM invoices WHERE status='open'")[0][0]
    res = run_statement(workspace, "after_migrate", SAMPLE_STATEMENT, timeout=SMALL_RUN_TIMEOUT, db=db)
    require_finished(res, "run on pre-migrated ledger")
    assert res.summary()["matched_lines"] == GT_SAMPLE["summary"]["matched_lines"]


def _schema_snapshot(db: Path) -> list[tuple]:
    return db_query(db, "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name")


def test_v1_ledger_is_upgraded_automatically_by_run(workspace, full_run):
    """An untouched schema-v1 ledger must be migrated on startup, reconcile the sample and serve lookups."""
    require_full_ok()
    db = workspace / "v1_ledger.db"
    build_v1_ledger(db)
    n_open = db_query(db, "SELECT COUNT(*) FROM invoices WHERE status='open'")[0][0]
    res = run_statement(workspace, "v1_run", SAMPLE_STATEMENT, timeout=SMALL_RUN_TIMEOUT, db=db)
    require_finished(res, "run on a schema-v1 ledger")
    got = res.outcomes()
    bad = [(k, GT_SAMPLE["lines"][k], got.get(k)) for k in GT_SAMPLE["lines"] if got.get(k) != GT_SAMPLE["lines"][k]]
    assert not bad, f"{len(bad)} of 200 lines differ on the upgraded v1 ledger: {bad[:8]}"
    assert db_query(db, "SELECT COUNT(*) FROM invoices WHERE status='open'")[0][0] == n_open - GT_SAMPLE["summary"]["matched_invoices"]
    # lookup through a formatting variant on the upgraded ledger
    iid, ref = _pick_invoice(db, "reference GLOB 'RE-2026-[0-9][0-9][0-9][0-9][0-9][0-9]' AND id > 1000")
    seq = int(ref.split("-")[-1])
    look = run_cli(["lookup", "--db", str(db), "--reference", f"re 2026/{seq:06d}"], timeout=SMALL_RUN_TIMEOUT)
    assert look.exit_code == 0, look.stderr
    assert [int(l.split("\t")[0]) for l in look.stdout.strip().splitlines()] == [iid]
    # the ledger is up to date now: another migrate changes neither schema nor data
    before_schema, before_paid = _schema_snapshot(db), db_query(db, "SELECT COUNT(*) FROM invoices WHERE status='paid'")[0][0]
    again = run_cli(["migrate", "--db", str(db)], timeout=SMALL_RUN_TIMEOUT)
    assert again.exit_code == 0, again.stderr
    assert _schema_snapshot(db) == before_schema, "migrate on an up-to-date ledger changed the schema"
    assert db_query(db, "SELECT COUNT(*) FROM invoices WHERE status='paid'")[0][0] == before_paid
    assert db_query(db, "SELECT COUNT(*) FROM match_results")[0][0] == GT_SAMPLE["summary"]["matched_invoices"]


def test_pipeline_stages_are_logged(full_run):
    """README / instruction: the parse, match and report stages log `stage=<name> ... elapsed=<seconds>s` to stderr."""
    require_finished(full_run, "full statement run")
    stage_lines = [l for l in full_run.stderr.splitlines() if re.search(r"stage=\S+.*elapsed=\d+(\.\d+)?s\b", l)]
    assert stage_lines, f"no `stage=<name> ... elapsed=<seconds>s` line on stderr; stderr tail:\n{full_run.stderr[-1500:]}"
    names = {m.group(1) for l in stage_lines for m in [re.search(r"stage=(\S+)", l)] if m}
    missing = {"parse", "match", "report"} - names
    assert not missing, f"stage timing line(s) missing on stderr for {sorted(missing)}; found stages {sorted(names)}"


def test_changes_md_names_the_work_done():
    """Instruction item 6: a short CHANGES.md naming the root causes (the B3 cap among them) and the changes."""
    changes = APP / "CHANGES.md"
    assert changes.is_file(), "CHANGES.md is missing from the workspace root"
    text = changes.read_text(encoding="utf-8", errors="replace")
    assert len(text.strip()) >= 200, "CHANGES.md is (nearly) empty"
    low = text.lower()
    assert re.search(r"\bb3\b|batch|sammel|pr-?418", low), "CHANGES.md does not mention the batch rule (B3 / PR-418 cap) at all"


def _pick_invoice(db: Path, where: str) -> tuple[int, str]:
    rows = db_query(db, f"SELECT id, reference FROM invoices WHERE {where} ORDER BY id LIMIT 1")
    assert rows, where
    return int(rows[0][0]), rows[0][1]


def _lookup_db(workspace: Path, name: str) -> Path:
    """A scratch ledger brought up to date the documented way before `lookup` is exercised."""
    db = fresh_db(workspace, name)
    mig = run_cli(["migrate", "--db", str(db)], timeout=SMALL_RUN_TIMEOUT)
    assert mig.exit_code == 0, mig.stderr
    return db


def test_lookup_accepts_any_formatting_variant(workspace):
    db = _lookup_db(workspace, "lookup")
    # ledger row stored canonically, queried with slash / unpadded / lower-case variants
    iid, ref = _pick_invoice(db, "reference GLOB 'RE-2026-[0-9][0-9][0-9][0-9][0-9][0-9]' AND id > 1000")
    seq = int(ref.split("-")[-1])
    for query in (f"re 2026/{seq:06d}", f"RE-2026-{seq}", f"RE2026-{seq:06d}", ref):
        res = run_cli(["lookup", "--db", str(db), "--reference", query], timeout=SMALL_RUN_TIMEOUT)
        assert res.exit_code == 0, f"lookup {query!r}: exit {res.exit_code} {res.stderr}"
        ids = [int(line.split("\t")[0]) for line in res.stdout.strip().splitlines()]
        assert ids == [iid], f"lookup {query!r} returned {ids}, expected [{iid}]"
    # ledger row stored with a slash, queried canonically
    iid2, ref2 = _pick_invoice(db, "reference LIKE 'RE-2026/%'")
    seq2 = int(ref2.split("/")[-1])
    res = run_cli(["lookup", "--db", str(db), "--reference", f"RE-2026-{seq2:06d}"], timeout=SMALL_RUN_TIMEOUT)
    assert res.exit_code == 0, res.stderr
    assert [int(l.split("\t")[0]) for l in res.stdout.strip().splitlines()] == [iid2]
    # ledger row stored unpadded, queried padded
    iid3, ref3 = _pick_invoice(db, "reference GLOB 'RE-2026-[1-9]*' AND length(reference) < 14")
    seq3 = int(ref3.split("-")[-1])
    res = run_cli(["lookup", "--db", str(db), "--reference", f"RE-2026-{seq3:06d}"], timeout=SMALL_RUN_TIMEOUT)
    assert res.exit_code == 0, res.stderr
    assert [int(l.split("\t")[0]) for l in res.stdout.strip().splitlines()] == [iid3]


def test_lookup_unknown_reference_exits_1(workspace):
    db = _lookup_db(workspace, "lookup_unknown")
    res = run_cli(["lookup", "--db", str(db), "--reference", "RE-2026-999999"], timeout=SMALL_RUN_TIMEOUT)
    assert res.exit_code == 1
    assert res.stdout.strip() == ""
    assert "Traceback" not in res.stderr, res.stderr


def test_missing_input_file_exits_2(workspace):
    db = fresh_db(workspace, "missing")
    res = run_cli(
        ["run", "--db", str(db), "--statement", str(workspace / "does_not_exist.csv"),
         "--customers", str(DATA / "customers.csv"), "--out", str(workspace / "missing_out")],
        timeout=SMALL_RUN_TIMEOUT,
    )
    assert res.exit_code == 2


def test_malformed_statement_exits_2(workspace):
    """README: exit 2 for bad input such as a malformed statement (here: a duplicated Umsatz-ID)."""
    db = fresh_db(workspace, "malformed")
    bad = workspace / "malformed.csv"
    with SAMPLE_STATEMENT.open(encoding="utf-8") as fh:
        head = [next(fh) for _ in range(6)]
    bad.write_text("".join(head + [head[3]]), encoding="utf-8")  # line 3 appears twice
    res = run_cli(
        ["run", "--db", str(db), "--statement", str(bad), "--customers", str(DATA / "customers.csv"),
         "--out", str(workspace / "malformed_out")],
        timeout=SMALL_RUN_TIMEOUT,
    )
    assert res.exit_code == 2, f"exit {res.exit_code}\n{res.stderr[-1500:]}"
    assert "Traceback" not in res.stderr, res.stderr


def test_visible_unit_suite_still_passes():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests_unit", "-q", "-p", "no:cacheprovider"],
        cwd=str(APP), capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]
    assert " passed" in proc.stdout
