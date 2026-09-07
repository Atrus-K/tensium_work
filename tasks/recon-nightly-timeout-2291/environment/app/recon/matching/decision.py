"""Turn ranked candidates into a single MatchResult with a reason code (section 7)."""
from __future__ import annotations

from typing import Sequence

from recon.matching import scoring
from recon.models import Candidate, MatchResult, StatementLine

REASON_DEBIT = "DEBIT"
REASON_INVOICE_CONSUMED = "INVOICE_CONSUMED"
REASON_NO_CANDIDATE = "NO_CANDIDATE"
REASONS: tuple[str, ...] = (REASON_DEBIT, REASON_INVOICE_CONSUMED, REASON_NO_CANDIDATE)


def decide(line: StatementLine, candidates: Sequence[Candidate], unavailable_reference_seen: bool) -> MatchResult:
    if not line.is_credit:
        return MatchResult(line=line, reason=REASON_DEBIT)
    chosen = scoring.best(candidates)
    if chosen is not None:
        return MatchResult(line=line, rule=chosen.rule, invoices=tuple(chosen.invoices))
    if unavailable_reference_seen:
        return MatchResult(line=line, reason=REASON_INVOICE_CONSUMED)
    return MatchResult(line=line, reason=REASON_NO_CANDIDATE)
