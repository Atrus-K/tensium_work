"""Matching parameters (docs/matching_rules.md section 9).

Changes to these values require Finance Operations sign-off.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MatchConfig:
    amount_tolerance_cents: int = 1
    fuzzy_max_distance: int = 2
    b2_window_days: int = 14
    batch_window_days: int = 60
    batch_max_run: int = 40
    batch_min_run: int = 2


DEFAULT_CONFIG = MatchConfig()

# PR-418 hotfix (INCIDENT-2291): the subset search in matching/batch.py is
# exponential, so customers with more open invoices than this are skipped.
# Follow-up ticket to replace the search was promised in the review.
BATCH_SUBSET_CAP = 12
