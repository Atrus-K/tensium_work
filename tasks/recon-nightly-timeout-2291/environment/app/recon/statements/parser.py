"""Parser for the bank's CSV export (semicolon separated, German number and date formats).

Columns (header row, UTF-8):
    Umsatz-ID;Buchungstag;Valutadatum;Auftraggeber;IBAN;Verwendungszweck;Betrag;Waehrung
"""
from __future__ import annotations

import csv
import re
from datetime import date, datetime
from pathlib import Path

from recon.models import StatementLine

REQUIRED_COLUMNS = (
    "Umsatz-ID",
    "Buchungstag",
    "Valutadatum",
    "Auftraggeber",
    "IBAN",
    "Verwendungszweck",
    "Betrag",
    "Waehrung",
)
_AMOUNT_RE = re.compile(r"^([+-]?)(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d{1,2}))?$")


class StatementError(ValueError):
    """Raised for malformed statement files."""


def parse_amount(text: str) -> int:
    """'1.234,56' -> 123456; '-12,5' -> -1250; '750' -> 75000."""
    cleaned = text.strip().replace(" ", "")
    m = _AMOUNT_RE.match(cleaned)
    if not m:
        raise StatementError(f"unparseable amount {text!r}")
    sign, whole, frac = m.groups()
    cents = int(whole.replace(".", "")) * 100 + int((frac or "0").ljust(2, "0"))
    return -cents if sign == "-" else cents


def parse_date(text: str) -> date:
    text = text.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise StatementError(f"unparseable date {text!r}")


def parse_statement(path: str | Path) -> list[StatementLine]:
    path = Path(path)
    lines: list[StatementLine] = []
    seen: set[str] = set()
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise StatementError(f"{path.name}: missing columns {missing}")
        for row_no, row in enumerate(reader, start=2):
            line_id = (row["Umsatz-ID"] or "").strip()
            if not line_id:
                raise StatementError(f"{path.name}:{row_no}: empty Umsatz-ID")
            if line_id in seen:
                raise StatementError(f"{path.name}:{row_no}: duplicate Umsatz-ID {line_id}")
            seen.add(line_id)
            try:
                lines.append(
                    StatementLine(
                        line_id=line_id,
                        booking_date=parse_date(row["Buchungstag"]),
                        value_date=parse_date(row["Valutadatum"] or row["Buchungstag"]),
                        remitter=(row["Auftraggeber"] or "").strip(),
                        iban=(row["IBAN"] or "").strip(),
                        purpose=(row["Verwendungszweck"] or "").strip(),
                        amount_cents=parse_amount(row["Betrag"]),
                        currency=(row["Waehrung"] or "EUR").strip() or "EUR",
                    )
                )
            except StatementError as exc:
                raise StatementError(f"{path.name}:{row_no}: {exc}") from None
    return lines


def processing_order(lines: list[StatementLine]) -> list[StatementLine]:
    """Section 6: ascending (booking_date, line_id), never file order."""
    return sorted(lines, key=lambda ln: (ln.booking_date, ln.line_id))
