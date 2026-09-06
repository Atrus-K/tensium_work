"""sqlite access layer: schema creation, deterministic loading from data/, typed readers."""
from __future__ import annotations

import csv
import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Iterable, Optional

from tessera.models import (
    Claim,
    DepreciationRule,
    LineItem,
    Policy,
    PolicyVersion,
    PromptPayRule,
    Sublimit,
)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def _opt(value: str) -> Optional[str]:
    return value if value not in ("", None) else None


def load_data_dir(conn: sqlite3.Connection, data_dir: str | Path) -> None:
    """Populate every table from the CSV/JSON files in *data_dir* (idempotent)."""
    data_dir = Path(data_dir)
    with conn:
        for table in ("payments", "line_items", "claims", "coverage_sublimits", "policy_versions",
                      "policies", "depreciation_schedule", "prompt_pay_rules", "holidays"):
            conn.execute(f"DELETE FROM {table}")
        conn.executemany(
            "INSERT INTO policies VALUES (?,?,?,?)",
            [(r["policy_id"], r["insured"], r["state"], r["dwelling_limit"]) for r in _rows(data_dir / "policies.csv")],
        )
        conn.executemany(
            "INSERT INTO policy_versions VALUES (?,?,?,?,?,?,?)",
            [(r["version_id"], r["policy_id"], r["effective_from"], _opt(r["effective_to"]), r["contents_limit"],
              r["flat_deductible"], _opt(r["wind_hail_deductible_pct"])) for r in _rows(data_dir / "policy_versions.csv")],
        )
        conn.executemany(
            "INSERT INTO coverage_sublimits VALUES (?,?,?)",
            [(r["version_id"], r["category"], r["sublimit"]) for r in _rows(data_dir / "coverage_sublimits.csv")],
        )
        conn.executemany(
            "INSERT INTO claims VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(r["claim_id"], r["policy_id"], r["occurrence_id"], r["claim_type"], r["peril"], r["loss_date"],
              r["fnol_date"], _opt(r["proof_of_loss_date"]), r["received_date"], r["status"]) for r in _rows(data_dir / "claims.csv")],
        )
        conn.executemany(
            "INSERT INTO line_items VALUES (?,?,?,?,?,?)",
            [(r["item_id"], r["claim_id"], r["category"], r["description"], r["rcv"], r["purchase_date"])
             for r in _rows(data_dir / "line_items.csv")],
        )
        conn.executemany(
            "INSERT INTO payments VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(r["payment_id"], r["claim_id"], r["occurrence_id"], r["batch"], r["payment_date"], _opt(r["policy_version_id"]),
              r["indemnity"], r["interest"], r["deductible_applied"], r["category_acv"]) for r in _rows(data_dir / "payments_history.csv")],
        )
        conn.executemany(
            "INSERT INTO depreciation_schedule VALUES (?,?,?,?)",
            [(r["category"], r["annual_pct"], r["max_pct"], int(r["min_age_months"])) for r in _rows(data_dir / "depreciation_schedule.csv")],
        )
        rules = json.loads((data_dir / "prompt_pay_rules.json").read_text())
        conn.executemany(
            "INSERT INTO prompt_pay_rules VALUES (?,?,?,?,?,?)",
            [(state, r["clock_start"], int(r["deadline_days"]), r["day_type"], str(r["annual_rate_pct"]), 1 if r["interest_applies"] else 0)
             for state, r in sorted(rules.items())],
        )
        holidays_file = next(iter(sorted(data_dir.glob("holidays_*.csv"))), None)
        if holidays_file is not None:
            conn.executemany("INSERT INTO holidays VALUES (?,?)", [(r["date"], r["name"]) for r in _rows(holidays_file)])


# ----------------------------------------------------------------------------
# typed readers
# ----------------------------------------------------------------------------

def _d(value) -> float:
    return float(value)


def _date(value) -> Optional[date]:
    return date.fromisoformat(value) if value else None


def get_policy(conn: sqlite3.Connection, policy_id: str) -> Policy:
    r = conn.execute("SELECT * FROM policies WHERE policy_id = ?", (policy_id,)).fetchone()
    if r is None:
        raise KeyError(f"unknown policy {policy_id}")
    return Policy(r["policy_id"], r["insured"], r["state"], _d(r["dwelling_limit"]))


def get_policy_versions(conn: sqlite3.Connection, policy_id: str) -> list[PolicyVersion]:
    rows = conn.execute(
        "SELECT * FROM policy_versions WHERE policy_id = ? ORDER BY effective_from, version_id", (policy_id,)
    ).fetchall()
    return [
        PolicyVersion(
            r["version_id"], r["policy_id"], _date(r["effective_from"]), _date(r["effective_to"]),
            _d(r["contents_limit"]), _d(r["flat_deductible"]),
            _d(r["wind_hail_deductible_pct"]) if r["wind_hail_deductible_pct"] is not None else None,
        )
        for r in rows
    ]


def get_sublimits(conn: sqlite3.Connection, version_id: str) -> list[Sublimit]:
    rows = conn.execute(
        "SELECT * FROM coverage_sublimits WHERE version_id = ? ORDER BY category", (version_id,)
    ).fetchall()
    return [Sublimit(r["version_id"], r["category"], _d(r["sublimit"])) for r in rows]


def _claim(r: sqlite3.Row) -> Claim:
    return Claim(
        r["claim_id"], r["policy_id"], r["occurrence_id"], r["claim_type"], r["peril"], _date(r["loss_date"]),
        _date(r["fnol_date"]), _date(r["proof_of_loss_date"]), _date(r["received_date"]), r["status"],
    )


def get_claims_for_batch(conn: sqlite3.Connection, batch: str) -> list[Claim]:
    """All claims received in the batch month."""
    rows = conn.execute(
        "SELECT * FROM claims WHERE substr(received_date, 1, 7) = ? ORDER BY claim_id", (batch,)
    ).fetchall()
    return [_claim(r) for r in rows]


def get_line_items(conn: sqlite3.Connection, claim_id: str) -> list[LineItem]:
    rows = conn.execute("SELECT * FROM line_items WHERE claim_id = ? ORDER BY item_id", (claim_id,)).fetchall()
    return [LineItem(r["item_id"], r["claim_id"], r["category"], r["description"], _d(r["rcv"]), _date(r["purchase_date"])) for r in rows]


def get_depreciation_schedule(conn: sqlite3.Connection) -> dict[str, DepreciationRule]:
    rows = conn.execute("SELECT * FROM depreciation_schedule").fetchall()
    return {r["category"]: DepreciationRule(r["category"], _d(r["annual_pct"]), _d(r["max_pct"]), int(r["min_age_months"])) for r in rows}


def get_prompt_pay_rules(conn: sqlite3.Connection) -> dict[str, PromptPayRule]:
    rows = conn.execute("SELECT * FROM prompt_pay_rules").fetchall()
    return {
        r["state"]: PromptPayRule(r["state"], r["clock_start"], int(r["deadline_days"]), r["day_type"], _d(r["annual_rate_pct"]), bool(r["interest_applies"]))
        for r in rows
    }


def get_holidays(conn: sqlite3.Connection) -> set[date]:
    return {date.fromisoformat(r["day"]) for r in conn.execute("SELECT day FROM holidays").fetchall()}


def iter_tables(conn: sqlite3.Connection) -> Iterable[str]:
    for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"):
        yield r["name"]
