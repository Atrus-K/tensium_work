"""Ranking of candidates (matching_rules.md section 5)."""
from __future__ import annotations

from typing import Sequence

from recon.models import Candidate

RULE_PRIORITY: dict[str, int] = {"A1": 0, "A2": 1, "B1": 2, "B2": 3, "B3": 4}


def candidate_key(cand: Candidate) -> tuple:
    first = min(cand.invoices, key=lambda inv: (inv.due_date, inv.id))
    return (RULE_PRIORITY[cand.rule], cand.amount_diff, cand.distance, first.due_date, first.id)


def rank(candidates: Sequence[Candidate]) -> list[Candidate]:
    return sorted(candidates, key=candidate_key)


def best(candidates: Sequence[Candidate]) -> Candidate | None:
    return min(candidates, key=candidate_key) if candidates else None
