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
