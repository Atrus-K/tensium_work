"""SQLite access. One connection per Repository instance, one commit per run."""
from __future__ import annotations

import logging
import sqlite3
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

from recon.matching.normalize import normalize_reference
from recon.models import Customer, Invoice, MatchResult, StatementLine
from recon.store import migrations

log = logging.getLogger("recon.store")


def _row_to_invoice(row: sqlite3.Row) -> Invoice:
    return Invoice(
        id=int(row["id"]),
        customer_id=int(row["customer_id"]),
        reference=row["reference"],
        amount_cents=int(row["amount_cents"]),
        currency=row["currency"],
        due_date=date.fromisoformat(row["due_date"]),
        status=row["status"],
    )


class Repository:
    """Context manager owning a single SQLite connection for the whole run."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._conn: sqlite3.Connection | None = None

    # -- lifecycle ---------------------------------------------------------
    def open(self) -> "Repository":
        if self._conn is None:
            log.debug("sqlite3 connect %s", self.path)
            conn = sqlite3.connect(str(self.path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._conn = conn
        return self

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Repository":
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("repository is not open")
        return self._conn

    def commit(self) -> None:
        self.conn.commit()

    def migrate(self) -> int:
        return migrations.apply_migrations(self.conn)

    # -- reads -------------------------------------------------------------
    def load_invoices(self, status: str | None = None) -> list[Invoice]:
        """Bulk-load invoices (all statuses by default) ordered by (due_date, id)."""
        sql = "SELECT id, customer_id, reference, amount_cents, currency, due_date, status FROM invoices"
        params: tuple = ()
        if status is not None:
            sql += " WHERE status = ?"
            params = (status,)
        sql += " ORDER BY due_date, id"
        return [_row_to_invoice(r) for r in self.conn.execute(sql, params)]

    def get_invoice(self, invoice_id: int) -> Invoice | None:
        row = self.conn.execute(
            "SELECT id, customer_id, reference, amount_cents, currency, due_date, status FROM invoices WHERE id = ?",
            (invoice_id,),
        ).fetchone()
        return _row_to_invoice(row) if row else None

    def open_invoices_for_customer(self, customer_id: int) -> list[Invoice]:
        rows = self.conn.execute(
            "SELECT id, customer_id, reference, amount_cents, currency, due_date, status FROM invoices "
            "WHERE customer_id = ? AND status = 'open' ORDER BY due_date, id",
            (customer_id,),
        )
        return [_row_to_invoice(r) for r in rows]

    def invoices_by_reference(self, reference: str) -> list[Invoice]:
        """Sargable lookup on the stored normalised reference (any formatting variant)."""
        rows = self.conn.execute(
            "SELECT id, customer_id, reference, amount_cents, currency, due_date, status FROM invoices "
            "WHERE reference_norm = ? ORDER BY due_date, id",
            (normalize_reference(reference),),
        )
        return [_row_to_invoice(r) for r in rows]

    def count(self, table: str) -> int:
        return int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    # -- writes ------------------------------------------------------------
    def insert_customers(self, customers: Iterable[Customer]) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO customers(customer_id, legal_name) VALUES (?, ?)",
            ((c.customer_id, c.legal_name) for c in customers),
        )

    def insert_invoices(self, invoices: Iterable[Invoice]) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO invoices(id, customer_id, reference, reference_norm, amount_cents, currency, due_date, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (
                    inv.id,
                    inv.customer_id,
                    inv.reference,
                    normalize_reference(inv.reference),
                    inv.amount_cents,
                    inv.currency,
                    inv.due_date.isoformat(),
                    inv.status,
                )
                for inv in invoices
            ),
        )

    def insert_bank_lines(self, lines: Sequence[StatementLine], statement_file: str) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO bank_lines(line_id, booking_date, value_date, remitter, iban, purpose, "
            "amount_cents, currency, statement_file) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (
                    ln.line_id,
                    ln.booking_date.isoformat(),
                    ln.value_date.isoformat(),
                    ln.remitter,
                    ln.iban,
                    ln.purpose,
                    ln.amount_cents,
                    ln.currency,
                    statement_file,
                )
                for ln in lines
            ),
        )

    def record_matches(self, results: Iterable[MatchResult]) -> int:
        """Write match_results rows and flip invoice status in bulk; caller commits."""
        rows = [
            (res.line.line_id, inv.id, res.rule, res.line.amount_cents)
            for res in results
            if res.matched
            for inv in res.invoices
        ]
        self.conn.executemany(
            "INSERT OR REPLACE INTO match_results(line_id, invoice_id, rule, amount_cents) VALUES (?, ?, ?, ?)",
            rows,
        )
        self.conn.executemany(
            "UPDATE invoices SET status = 'paid' WHERE id = ?",
            ((r[1],) for r in rows),
        )
        return len(rows)
