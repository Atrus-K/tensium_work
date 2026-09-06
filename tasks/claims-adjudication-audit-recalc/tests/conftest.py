"""Fixtures: build a fresh sqlite DB from a data directory via the public CLI,
adjudicate the batch twice, and expose the exports / ledger rows."""
from __future__ import annotations

import csv
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

import oracle

APP_DIR = Path(os.environ.get("TESSERA_APP_DIR", os.getcwd())).resolve()
TESTS_DIR = Path(__file__).resolve().parent
MAIN_DATA = APP_DIR / "data"
ALT_DATA = TESTS_DIR / "fixtures" / "alt_dataset"

EXPORT_COLUMNS = [
    "claim_id", "occurrence_id", "policy_id", "state", "policy_version_id", "status", "gross_acv",
    "sublimit_reduction", "deductible_applied", "indemnity", "days_late", "interest", "payment_total",
]


def cli(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        [sys.executable, "-m", "tessera.cli", *args],
        cwd=str(APP_DIR), capture_output=True, text=True, timeout=300,
    )
    if check and proc.returncode != 0:
        raise AssertionError(f"tessera.cli {' '.join(args)} failed ({proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
    return proc


def read_export(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    return {r["claim_id"]: r for r in rows}, reader.fieldnames


def read_payments(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in conn.execute("SELECT * FROM payments ORDER BY payment_id").fetchall()]
    finally:
        conn.close()
    return rows


def D(value) -> Decimal:
    return Decimal(str(value))


@dataclass
class Run:
    name: str
    data_dir: Path
    batch: str
    as_of: date
    db_path: Path
    export1: Path
    export2: Path
    rows: dict = field(default_factory=dict)
    columns: list = field(default_factory=list)
    payments_after_first: list = field(default_factory=list)
    payments_after_second: list = field(default_factory=list)
    dataset: oracle.Dataset | None = None
    expected: dict = field(default_factory=dict)

    # ------------------------------------------------------------ helpers
    def payments_for_claim(self, claim_id: str) -> list[dict]:
        return [p for p in self.payments_after_second if p["claim_id"] == claim_id]

    def payments_for_occurrence(self, occurrence_id: str) -> list[dict]:
        return [p for p in self.payments_after_second if p["occurrence_id"] == occurrence_id]

    def batch_claim_ids(self) -> list[str]:
        return [c["claim_id"] for c in self.dataset.claims if c["received_date"][:7] == self.batch]


def _make_run(tmp_root: Path, name: str, data_dir: Path, batch: str, as_of: date) -> Run:
    work = tmp_root / name
    work.mkdir(parents=True, exist_ok=True)
    db_path = work / "claims.db"
    export1 = work / "export_run1.csv"
    export2 = work / "export_run2.csv"
    cli("build-db", "--data", str(data_dir), "--out", str(db_path))
    cli("adjudicate", "--db", str(db_path), "--as-of", as_of.isoformat(), "--batch", batch, "--out", str(export1))
    payments1 = read_payments(db_path)
    cli("adjudicate", "--db", str(db_path), "--as-of", as_of.isoformat(), "--batch", batch, "--out", str(export2))
    payments2 = read_payments(db_path)
    rows, columns = read_export(export1)
    ds = oracle.load(data_dir)
    run = Run(name, data_dir, batch, as_of, db_path, export1, export2, rows, columns, payments1, payments2, ds,
              oracle.compute_batch(ds, batch, as_of))
    return run


@pytest.fixture(scope="session")
def main_run(tmp_path_factory) -> Run:
    return _make_run(tmp_path_factory.mktemp("tessera"), "main", MAIN_DATA, "2024-06", date(2024, 6, 30))


@pytest.fixture(scope="session")
def alt_run(tmp_path_factory) -> Run:
    return _make_run(tmp_path_factory.mktemp("tessera"), "alt", ALT_DATA, "2024-07", date(2024, 7, 15))


@pytest.fixture(scope="session", params=["main", "alt"])
def any_run(request, main_run, alt_run) -> Run:
    return main_run if request.param == "main" else alt_run
