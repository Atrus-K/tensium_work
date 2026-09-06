"""Rule B3 — batch payments (matching_rules.md section 4, B3).

A run is a *contiguous* slice of the customer's available invoices in
(due_date, id) order whose amounts sum to the payment, spans at most the
configured window and has between min and max invoices. Earliest start wins,
then the shortest run.
"""
from __future__ import annotations

from typing import Sequence

from recon.config import DEFAULT_CONFIG, MatchConfig
from recon.models import Invoice


def oldest_first(invoices: Sequence[Invoice]) -> list[Invoice]:
    return sorted(invoices, key=lambda inv: (inv.due_date, inv.id))


def find_batch(
    invoices: Sequence[Invoice], amount_cents: int, config: MatchConfig = DEFAULT_CONFIG
) -> list[Invoice] | None:
    """Return the winning run for ``amount_cents`` or None. Linear in runs, not subsets."""
    invs = oldest_first(invoices)
    n = len(invs)
    if n < config.batch_min_run:
        return None
    tol = config.amount_tolerance_cents
    prefix = [0] * (n + 1)
    for idx, inv in enumerate(invs):
        prefix[idx + 1] = prefix[idx] + inv.amount_cents
    upper = amount_cents + tol
    for i in range(n - config.batch_min_run + 1):
        start_due = invs[i].due_date
        last = min(n, i + config.batch_max_run)
        for j in range(i + config.batch_min_run - 1, last):
            if (invs[j].due_date - start_due).days > config.batch_window_days:
                break
            total = prefix[j + 1] - prefix[i]
            if total > upper:
                break  # amounts are positive: longer runs only grow
            if abs(total - amount_cents) <= tol:
                return invs[i : j + 1]
    return None
