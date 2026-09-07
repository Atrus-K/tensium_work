"""Candidate generation for rules A1, A2, B1, B2, B3 (matching_rules.md section 4).

The ledger is scanned once per statement line; consumed invoices (section 6)
are skipped via the ``consumed`` id set maintained by the pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from recon.config import DEFAULT_CONFIG, MatchConfig
from recon.matching import batch
from recon.matching.fuzzy import levenshtein
from recon.matching.normalize import normalize_reference
from recon.models import Candidate, Customer, Invoice, StatementLine
from recon.store.repository import Repository

RULES: tuple[str, ...] = ("A1", "A2", "B1", "B2", "B3")


@dataclass
class CandidateScan:
    candidates: list[Candidate] = field(default_factory=list)
    # a token named an invoice that is paid or already consumed (reason code INVOICE_CONSUMED)
    unavailable_reference_seen: bool = False


def _amount_ok(a: int, b: int, config: MatchConfig) -> bool:
    return abs(a - b) <= config.amount_tolerance_cents


def scan_references(
    line: StatementLine, tokens: Sequence[str], repo: Repository, consumed: set[int], config: MatchConfig
) -> CandidateScan:
    """Rules A1 and A2 over the whole ledger."""
    scan = CandidateScan()
    token_set = set(tokens)
    for invoice_id in repo.all_invoice_ids():
        inv = repo.get_invoice(invoice_id)
        norm = normalize_reference(inv.reference)
        diff = abs(inv.amount_cents - line.amount_cents)
        if not inv.is_open or inv.id in consumed:
            if norm in token_set:
                scan.unavailable_reference_seen = True
            continue
        if norm in token_set:
            if diff <= config.amount_tolerance_cents:
                scan.candidates.append(Candidate("A1", (inv,), diff, 0))
            continue
        if tokens:
            distance = min(levenshtein(tok, norm) for tok in tokens)
            if distance <= config.fuzzy_max_distance and diff <= config.amount_tolerance_cents:
                scan.candidates.append(Candidate("A2", (inv,), diff, distance))
    return scan


def _available(repo: Repository, customer: Customer, consumed: set[int]) -> list[Invoice]:
    return [inv for inv in repo.open_invoices_for_customer(customer.customer_id) if inv.id not in consumed]


def rule_b1(line: StatementLine, customer: Customer | None, repo: Repository, consumed: set[int], config: MatchConfig) -> list[Candidate]:
    if customer is None:
        return []
    return [
        Candidate("B1", (inv,), abs(inv.amount_cents - line.amount_cents), 0)
        for inv in _available(repo, customer, consumed)
        if _amount_ok(inv.amount_cents, line.amount_cents, config)
    ]


def rule_b2(line: StatementLine, customer: Customer | None, repo: Repository, consumed: set[int], config: MatchConfig) -> list[Candidate]:
    if customer is None:
        return []
    return [
        Candidate("B2", (inv,), abs(inv.amount_cents - line.amount_cents), 0)
        for inv in _available(repo, customer, consumed)
        if _amount_ok(inv.amount_cents, line.amount_cents, config)
        and abs((inv.due_date - line.booking_date).days) <= config.b2_window_days
    ]


def rule_b3(line: StatementLine, customer: Customer | None, repo: Repository, consumed: set[int], config: MatchConfig) -> list[Candidate]:
    if customer is None:
        return []
    run = batch.find_batch(_available(repo, customer, consumed), line.amount_cents, config)
    if not run:
        return []
    total = sum(inv.amount_cents for inv in run)
    return [Candidate("B3", tuple(run), abs(total - line.amount_cents), 0)]


def find_candidates(
    line: StatementLine,
    tokens: Sequence[str],
    repo: Repository,
    customer_by_iban: Customer | None,
    customer_by_name: Customer | None,
    consumed: set[int],
    config: MatchConfig = DEFAULT_CONFIG,
) -> CandidateScan:
    """Candidates of the first rule (in A1..B3 order) that produces any."""
    scan = scan_references(line, tokens, repo, consumed, config)
    if scan.candidates:
        return scan
    for cands in (
        rule_b1(line, customer_by_iban, repo, consumed, config),
        rule_b2(line, customer_by_name, repo, consumed, config),
        rule_b3(line, customer_by_iban or customer_by_name, repo, consumed, config),
    ):
        if cands:
            scan.candidates = cands
            break
    return scan
