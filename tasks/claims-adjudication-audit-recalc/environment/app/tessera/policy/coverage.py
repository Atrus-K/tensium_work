"""Coverage terms of a policy version: limit, deductible and category sublimits."""
from __future__ import annotations

from typing import Iterable

from tessera.adjudication.rounding import round_cents
from tessera.models import PolicyVersion, Sublimit


def deductible_for(version: PolicyVersion) -> float:
    """Deductible for a claim under a version."""
    return round_cents(version.flat_deductible)


def sublimit_map(sublimits: Iterable[Sublimit]) -> dict[str, float]:
    """{category: sublimit} for a version."""
    return {s.category: round_cents(s.amount) for s in sublimits}


def contents_limit(version: PolicyVersion) -> float:
    return round_cents(version.contents_limit)
