"""Plain data records shared by all stages."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class StatementLine:
    line_id: str
    booking_date: date
    value_date: date
    remitter: str
    iban: str
    purpose: str
    amount_cents: int
    currency: str = "EUR"

    @property
    def is_credit(self) -> bool:
        return self.amount_cents > 0


@dataclass(frozen=True)
class Invoice:
    id: int
    customer_id: int
    reference: str
    amount_cents: int
    currency: str
    due_date: date
    status: str  # "open" | "paid"

    @property
    def is_open(self) -> bool:
        return self.status == "open"


@dataclass(frozen=True)
class Customer:
    customer_id: int
    legal_name: str
    aliases: tuple[str, ...] = ()
    ibans: tuple[str, ...] = ()

    @property
    def names(self) -> tuple[str, ...]:
        return (self.legal_name, *self.aliases)


@dataclass(frozen=True)
class Candidate:
    """One possible match for a statement line under a given rule."""

    rule: str
    invoices: tuple[Invoice, ...]
    amount_diff: int = 0
    distance: int = 0

    @property
    def invoice_ids(self) -> tuple[int, ...]:
        return tuple(sorted(inv.id for inv in self.invoices))


@dataclass(frozen=True)
class MatchResult:
    line: StatementLine
    rule: str | None = None
    invoices: tuple[Invoice, ...] = field(default_factory=tuple)
    reason: str | None = None

    @property
    def matched(self) -> bool:
        return self.rule is not None

    @property
    def invoice_ids(self) -> tuple[int, ...]:
        return tuple(sorted(inv.id for inv in self.invoices))
