"""Shared fixtures: run the documented CLI in a scratch copy of the workspace data.

Everything is observed through the CLI, the report files and the SQLite
database, never through internal names of the application.
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES = TESTS_DIR / "fixtures"
HARNESS = TESTS_DIR / "harness"


def _app_dir() -> Path:
    env = os.environ.get("RECON_APP_DIR")
    if env:
        return Path(env)
    if Path("/app/recon").is_dir():
        return Path("/app")
    return TESTS_DIR.parent / "environment" / "app"


APP = _app_dir()
DATA = APP / "data"
FULL_STATEMENT = DATA / "statements" / "nordwind_2026-08.csv"
SAMPLE_STATEMENT = DATA / "statements" / "sample_200.csv"
ALT_STATEMENT = FIXTURES / "alt_statement_2026-09.csv"

FULL_RUN_TIMEOUT = 150.0  # seconds before the child is killed (the budget itself is asserted separately)
SMALL_RUN_TIMEOUT = 120.0
FULL_RUN_BUDGET = 60.0
SQL_STATEMENT_BUDGET = 300_000

_STATE: dict[str, bool] = {"full_timed_out": False}


@dataclass
class RunResult:
    args: list[str]
    exit_code: int | None
    elapsed: float
    stdout: str
    stderr: str
    timed_out: bool
    out_dir: Path | None = None
    db_path: Path | None = None
    sql_connects: int | None = None
    sql_statements: int | None = None
    extra: dict = field(default_factory=dict)

    # -- report helpers ------------------------------------------------------
    def matches(self) -> dict[str, dict]:
        rows = {}
        with (self.out_dir / "matches.csv").open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                rows[r["line_id"]] = r
        return rows

    def unmatched(self) -> dict[str, dict]:
        rows = {}
        with (self.out_dir / "unmatched.csv").open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                rows[r["line_id"]] = r
        return rows

    def summary(self) -> dict:
        return json.loads((self.out_dir / "summary.json").read_text(encoding="utf-8"))

    def outcomes(self) -> dict[str, dict]:
        """Per line: {"rule", "invoice_ids"} or {"reason"} — same shape as the ground truth."""
        out: dict[str, dict] = {}
        for lid, r in self.matches().items():
            out[lid] = {"rule": r["rule"], "invoice_ids": sorted(int(x) for x in r["invoice_ids"].split("|") if x)}
        for lid, r in self.unmatched().items():
            out[lid] = {"reason": r["reason"]}
        return out


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def run_cli(args: list[str], timeout: float, trace_file: Path | None = None, cwd: Path = APP) -> RunResult:
    env = dict(os.environ)
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    if trace_file is not None:
        env["PYTHONPATH"] = str(HARNESS) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        env["RECON_SQL_TRACE_FILE"] = str(trace_file)
        if trace_file.exists():
            trace_file.unlink()
    cmd = [sys.executable, "-m", "recon.cli", *args]
    t0 = time.perf_counter()
    proc = subprocess.Popen(
        cmd, cwd=str(cwd), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True
    )
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_group(proc)
        stdout, stderr = "", f"[tests] killed after {timeout:.0f}s"
    elapsed = time.perf_counter() - t0
    res = RunResult(args, None if timed_out else proc.returncode, elapsed, stdout, stderr, timed_out)
    if trace_file is not None and trace_file.exists():
        connects = statements = 0
        for line in trace_file.read_text().splitlines():
            parts = line.split()
            if len(parts) == 3:
                connects += int(parts[1])
                statements += int(parts[2])
        res.sql_connects, res.sql_statements = connects, statements
    return res


def fresh_db(workspace: Path, name: str) -> Path:
    dst = workspace / f"{name}.db"
    for suffix in ("", "-wal", "-shm", "-journal"):
        p = Path(str(dst) + suffix)
        if p.exists():
            p.unlink()
    shutil.copy(DATA / "recon.db", dst)
    return dst


def run_statement(workspace: Path, name: str, statement: Path, timeout: float, trace: bool = False,
                  db: Path | None = None) -> RunResult:
    db_path = db or fresh_db(workspace, name)
    out_dir = workspace / f"{name}_out"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    trace_file = workspace / f"{name}.sqltrace" if trace else None
    res = run_cli(
        ["run", "--db", str(db_path), "--statement", str(statement), "--customers", str(DATA / "customers.csv"),
         "--out", str(out_dir)],
        timeout=timeout,
        trace_file=trace_file,
    )
    res.out_dir, res.db_path = out_dir, db_path
    return res


def require_finished(res: RunResult, what: str) -> None:
    if res.timed_out:
        pytest.fail(f"{what} did not finish within {FULL_RUN_TIMEOUT:.0f}s and was killed")
    if res.exit_code != 0:
        pytest.fail(f"{what} exited with {res.exit_code}\nstdout:\n{res.stdout[-2000:]}\nstderr:\n{res.stderr[-4000:]}")


def require_full_ok() -> None:
    if _STATE["full_timed_out"]:
        pytest.fail("the full statement run did not finish; dependent run skipped to save verifier time")


def load_gt(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def db_query(path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def statement_lines(path: Path) -> dict[str, dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return {r["Umsatz-ID"]: r for r in csv.DictReader(fh, delimiter=";")}


def german_to_cents(text: str) -> int:
    text = text.strip()
    neg = text.startswith("-")
    text = text.lstrip("+-").replace(".", "")
    whole, _, frac = text.partition(",")
    cents = int(whole) * 100 + int((frac or "0").ljust(2, "0"))
    return -cents if neg else cents


# --------------------------------------------------------------------------- #
# session fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def workspace(tmp_path_factory) -> Path:
    ws = tmp_path_factory.mktemp("recon_ws")
    assert (DATA / "recon.db").is_file(), f"ledger not found at {DATA / 'recon.db'}"
    return ws


@pytest.fixture(scope="session")
def full_run(workspace) -> RunResult:
    res = run_statement(workspace, "full", FULL_STATEMENT, timeout=FULL_RUN_TIMEOUT, trace=True)
    _STATE["full_timed_out"] = res.timed_out or res.exit_code != 0
    return res


@pytest.fixture(scope="session")
def full_rerun_fresh(workspace, full_run) -> RunResult:
    """Second run of the full statement on a fresh copy of the ledger (determinism)."""
    require_full_ok()
    return run_statement(workspace, "full2", FULL_STATEMENT, timeout=FULL_RUN_TIMEOUT)


@pytest.fixture(scope="session")
def full_rerun_same_db(workspace, full_run) -> RunResult:
    """Run the full statement again against the ledger the first run already reconciled."""
    require_full_ok()
    return run_statement(workspace, "full_same", FULL_STATEMENT, timeout=FULL_RUN_TIMEOUT, db=full_run.db_path)


@pytest.fixture(scope="session")
def alt_run(workspace, full_run) -> RunResult:
    require_full_ok()
    return run_statement(workspace, "alt", ALT_STATEMENT, timeout=SMALL_RUN_TIMEOUT)


@pytest.fixture(scope="session")
def sample_run(workspace, full_run) -> RunResult:
    require_full_ok()
    return run_statement(workspace, "sample", SAMPLE_STATEMENT, timeout=SMALL_RUN_TIMEOUT)
