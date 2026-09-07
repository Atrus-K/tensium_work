"""SQLite access for the ledger.

Each call opens its own short-lived connection so the repository is safe to use
from any stage without sharing state.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import date
from pathlib import Path
from typing import Iterable

from recon.models import Customer, Invoice, MatchResult, StatementLine
from recon.store import migrations

log = logging.getLogger("recon.store")

_INVOICE_COLUMNS = "id, customer_id, reference, amount_cents, currency, due_date, status"


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


def _sql_mirror(reference: str) -> str:
    """Python side of the normalisation used in invoices_by_reference's WHERE clause."""
    return reference.lower().replace("-", "").replace(" ", "")


class Repository:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def __enter__(self) -> "Repository":
        return self

    def __exit__(self, *exc) -> None:
        return None

    def _connect(self) -> sqlite3.Connection:
        log.debug("sqlite3 connect %s", self.path)
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    def migrate(self) -> int:
        conn = self._connect()
        try:
            return migrations.apply_migrations(conn)
        finally:
            conn.close()

    # -- reads -------------------------------------------------------------
    def all_invoice_ids(self) -> list[int]:
        conn = self._connect()
        try:
            return [int(r[0]) for r in conn.execute("SELECT id FROM invoices ORDER BY id")]
        finally:
            conn.close()

    def all_open_invoice_ids(self) -> list[int]:
        conn = self._connect()
        try:
            return [int(r[0]) for r in conn.execute("SELECT id FROM invoices WHERE status = 'open' ORDER BY id")]
        finally:
            conn.close()

    def get_invoice(self, invoice_id: int) -> Invoice | None:
        conn = self._connect()
        try:
            row = conn.execute(f"SELECT {_INVOICE_COLUMNS} FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
            return _row_to_invoice(row) if row else None
        finally:
            conn.close()

    def open_invoices_for_customer(self, customer_id: int) -> list[Invoice]:
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT {_INVOICE_COLUMNS} FROM invoices WHERE customer_id = ? AND status = 'open' ORDER BY due_date, id",
                (customer_id,),
            )
            return [_row_to_invoice(r) for r in rows]
        finally:
            conn.close()

    def invoices_by_reference(self, reference: str) -> list[Invoice]:
        """Look up invoices by reference regardless of hyphens/spaces/case (used by `lookup`)."""
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT {_INVOICE_COLUMNS} FROM invoices "
                "WHERE lower(replace(replace(reference, '-', ''), ' ', '')) = ? ORDER BY due_date, id",
                (_sql_mirror(reference),),
            )
            return [_row_to_invoice(r) for r in rows]
        finally:
            conn.close()

    def count(self, table: str) -> int:
        conn = self._connect()
        try:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        finally:
            conn.close()

    # -- writes ------------------------------------------------------------
    def insert_customers(self, customers: Iterable[Customer]) -> None:
        conn = self._connect()
        try:
            conn.executemany(
                "INSERT OR REPLACE INTO customers(customer_id, legal_name) VALUES (?, ?)",
                ((c.customer_id, c.legal_name) for c in customers),
            )
            conn.commit()
        finally:
            conn.close()

    def insert_invoices(self, invoices: Iterable[Invoice]) -> None:
        conn = self._connect()
        try:
            conn.executemany(
                "INSERT OR REPLACE INTO invoices(id, customer_id, reference, amount_cents, currency, due_date, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    (inv.id, inv.customer_id, inv.reference, inv.amount_cents, inv.currency, inv.due_date.isoformat(), inv.status)
                    for inv in invoices
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def insert_bank_line(self, line: StatementLine, statement_file: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO bank_lines(line_id, booking_date, value_date, remitter, iban, purpose, "
                "amount_cents, currency, statement_file) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    line.line_id,
                    line.booking_date.isoformat(),
                    line.value_date.isoformat(),
                    line.remitter,
                    line.iban,
                    line.purpose,
                    line.amount_cents,
                    line.currency,
                    statement_file,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def mark_matched(self, result: MatchResult) -> int:
        """Write match_results rows for one line and flip the invoices to paid."""
        if not result.matched:
            return 0
        conn = self._connect()
        try:
            for inv in result.invoices:
                conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (inv.id,))
                conn.execute(
                    "INSERT OR REPLACE INTO match_results(line_id, invoice_id, rule, amount_cents) VALUES (?, ?, ?, ?)",
                    (result.line.line_id, inv.id, result.rule, result.line.amount_cents),
                )
                conn.commit()
            return len(result.invoices)
        finally:
            conn.close()
