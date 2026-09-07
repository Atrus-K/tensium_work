"""Per-line processing: identify customer -> candidates -> decision -> consumption (section 6)."""
from __future__ import annotations

import logging
from pathlib import Path

from recon.config import DEFAULT_CONFIG, MatchConfig
from recon.customers.master import identify_by_iban, identify_by_name
from recon.matching.candidates import CandidateScan, find_candidates
from recon.matching.decision import decide
from recon.matching.normalize import extract_reference_tokens
from recon.models import MatchResult, StatementLine
from recon.store.repository import Repository

log = logging.getLogger("recon.pipeline")


def process_line(
    line: StatementLine,
    repo: Repository,
    customers_path: str | Path,
    consumed: set[int],
    config: MatchConfig = DEFAULT_CONFIG,
) -> MatchResult:
    tokens = extract_reference_tokens(line.purpose)
    by_iban = identify_by_iban(line.iban, customers_path)
    by_name = identify_by_name(line.remitter, customers_path)
    log.debug(
        "line=%s tokens=%s customer_iban=%s customer_name=%s",
        line.line_id,
        tokens,
        by_iban.customer_id if by_iban else None,
        by_name.customer_id if by_name else None,
    )
    if line.is_credit:
        scan = find_candidates(line, tokens, repo, by_iban, by_name, consumed, config)
    else:
        scan = CandidateScan()
    result = decide(line, scan.candidates, scan.unavailable_reference_seen)
    if result.matched:
        consumed.update(inv.id for inv in result.invoices)
    return result
