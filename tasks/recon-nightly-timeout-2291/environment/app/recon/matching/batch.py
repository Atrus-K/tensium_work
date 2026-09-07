"""Rule B3 — batch payments (matching_rules.md section 4, B3).

Searches the customer's open invoices for a combination whose amounts sum to
the payment. Customers with more than BATCH_SUBSET_CAP open invoices are
skipped since PR-418 (the search is exponential in the number of invoices).
"""
from __future__ import annotations

import logging
from itertools import combinations
from typing import Sequence

from recon.config import BATCH_SUBSET_CAP, DEFAULT_CONFIG, MatchConfig
from recon.models import Invoice

log = logging.getLogger("recon.matching.batch")


def oldest_first(invoices: Sequence[Invoice]) -> list[Invoice]:
    return sorted(invoices, key=lambda inv: (inv.due_date, inv.id))


def find_batch(
    invoices: Sequence[Invoice], amount_cents: int, config: MatchConfig = DEFAULT_CONFIG
) -> list[Invoice] | None:
    """Return the invoices paid by ``amount_cents`` together, or None."""
    invs = oldest_first(invoices)
    if len(invs) < config.batch_min_run:
        return None
    if len(invs) > BATCH_SUBSET_CAP:
        log.warning("batch: candidate set %d > %d, skipping (PR-418 cap)", len(invs), BATCH_SUBSET_CAP)
        return None
    tol = config.amount_tolerance_cents
    for size in range(config.batch_min_run, min(len(invs), config.batch_max_run) + 1):
        for combo in combinations(invs, size):
            total = sum(inv.amount_cents for inv in combo)
            if abs(total - amount_cents) > tol:
                continue
            span = (max(inv.due_date for inv in combo) - min(inv.due_date for inv in combo)).days
            if span <= config.batch_window_days:
                return list(combo)
    return None
