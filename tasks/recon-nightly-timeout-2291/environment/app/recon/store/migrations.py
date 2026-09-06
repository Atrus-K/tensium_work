"""Schema versioning. `apply_migrations` is run on every startup and is a no-op
for a database that is already at the current version.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from recon.matching.normalize import normalize_reference

log = logging.getLogger("recon.store")
_HERE = Path(__file__).parent


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _v2_reference_norm(conn: sqlite3.Connection) -> None:
    """Add invoices.reference_norm and fill it with the Python normaliser."""
    if "reference_norm" not in _column_names(conn, "invoices"):
        conn.execute("ALTER TABLE invoices ADD COLUMN reference_norm TEXT")
    backfill_reference_norm(conn)


def backfill_reference_norm(conn: sqlite3.Connection) -> int:
    """Fill reference_norm where missing, using the one and only normaliser.

    Runs as a single UPDATE with the Python function registered on the
    connection so the ledger and the matcher can never disagree on a value.
    """
    conn.create_function("recon_normalize", 1, normalize_reference, deterministic=True)
    cur = conn.execute(
        "UPDATE invoices SET reference_norm = recon_normalize(reference) "
        "WHERE reference_norm IS NULL OR reference_norm != recon_normalize(reference)"
    )
    return cur.rowcount


@dataclass(frozen=True)
class Migration:
    version: int
    sql_file: str | None = None
    python: Callable[[sqlite3.Connection], None] | None = None


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, sql_file="schema.sql"),
    Migration(2, python=_v2_reference_norm, sql_file="schema_v2.sql"),
)
CURRENT_VERSION = MIGRATIONS[-1].version


def current_version(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Bring the database to CURRENT_VERSION; returns the number of migrations applied."""
    applied = 0
    version = current_version(conn)
    for mig in MIGRATIONS:
        if mig.version <= version:
            continue
        log.info("migrating schema %d -> %d", version, mig.version)
        if mig.python is not None:
            mig.python(conn)
        if mig.sql_file:
            conn.executescript((_HERE / mig.sql_file).read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_version(version) VALUES (?)", (mig.version,))
        conn.commit()
        version = mig.version
        applied += 1
    return applied
