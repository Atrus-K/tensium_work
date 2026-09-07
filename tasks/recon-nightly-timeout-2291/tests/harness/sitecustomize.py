"""Test-only interpreter hook: counts SQLite connections and executed statements.

Activated by putting this directory on PYTHONPATH and setting
RECON_SQL_TRACE_FILE. Every sqlite3 connection created through
sqlite3.connect (any import style: the module attribute is replaced before
application code imports) gets a trace callback; totals are appended to the
trace file at interpreter exit as "<pid> <connects> <statements>".
"""
import atexit
import os
import sqlite3

_trace_path = os.environ.get("RECON_SQL_TRACE_FILE")

if _trace_path:
    _counts = {"connects": 0, "statements": 0}
    _orig_connect = sqlite3.connect

    def _on_statement(_sql: str) -> None:
        _counts["statements"] += 1

    def _connect(*args, **kwargs):
        conn = _orig_connect(*args, **kwargs)
        _counts["connects"] += 1
        try:
            conn.set_trace_callback(_on_statement)
        except Exception:  # noqa: BLE001 - never break the application
            pass
        return conn

    sqlite3.connect = _connect
    try:
        import sqlite3.dbapi2 as _dbapi2

        _dbapi2.connect = _connect
    except Exception:  # noqa: BLE001
        pass

    def _flush() -> None:
        try:
            with open(_trace_path, "a", encoding="utf-8") as fh:
                fh.write(f"{os.getpid()} {_counts['connects']} {_counts['statements']}\n")
        except OSError:
            pass

    atexit.register(_flush)
