"""Test-only interpreter hook: counts SQLite connections and executed statements.

Activated by putting this directory on PYTHONPATH and setting
RECON_SQL_TRACE_FILE. It runs at interpreter start-up, before any application
module is imported, so every way of obtaining a connection is covered:
``sqlite3.connect``, ``from sqlite3 import connect``, ``sqlite3.dbapi2.connect``,
a custom ``factory=`` and direct ``sqlite3.Connection(...)`` construction.
Child interpreters inherit the environment and report their own totals, so a
solution that opens the ledger in a subprocess is counted too. Totals are
appended to the trace file at interpreter exit as "<pid> <connects> <statements>".
"""
import atexit
import os
import sqlite3

_trace_path = os.environ.get("RECON_SQL_TRACE_FILE")

if _trace_path:
    _counts = {"connects": 0, "statements": 0}
    _orig_connect = sqlite3.connect
    _OrigConnection = sqlite3.Connection

    def _on_statement(_sql: str) -> None:
        _counts["statements"] += 1

    def _attach(conn) -> None:
        _counts["connects"] += 1
        try:
            conn.set_trace_callback(_on_statement)
        except Exception:  # noqa: BLE001 - never break the application
            pass

    class _TracedConnection(_OrigConnection):
        """Replacement for sqlite3.Connection: counts itself when constructed directly."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            _attach(self)

    def _connect(*args, **kwargs):
        # Default connections become instances of the (replaced) sqlite3.Connection so
        # ``isinstance(conn, sqlite3.Connection)`` keeps working in application code.
        if "factory" not in kwargs and len(args) < 6:
            kwargs["factory"] = _TracedConnection
        conn = _orig_connect(*args, **kwargs)
        if not isinstance(conn, _TracedConnection):
            _attach(conn)
        return conn

    sqlite3.connect = _connect
    sqlite3.Connection = _TracedConnection
    try:
        import sqlite3.dbapi2 as _dbapi2

        _dbapi2.connect = _connect
        _dbapi2.Connection = _TracedConnection
    except Exception:  # noqa: BLE001
        pass

    def _flush() -> None:
        try:
            with open(_trace_path, "a", encoding="utf-8") as fh:
                fh.write(f"{os.getpid()} {_counts['connects']} {_counts['statements']}\n")
        except OSError:
            pass

    atexit.register(_flush)
