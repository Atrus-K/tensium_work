"""Select the policy version that applies to a claim.

The version whose in-force period contains the date the claim was received for
adjudication is used.  Since PLAT-355 a claim that matches no version no longer
aborts the batch: we fall back to the policy's latest version and log a WARN so
the batch can complete and the case can be reviewed afterwards.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional, Sequence

from tessera.models import PolicyVersion

log = logging.getLogger("tessera.lookup")


def is_in_force(version: PolicyVersion, on: date) -> bool:
    if on < version.effective_from:
        return False
    if version.effective_to is not None and on > version.effective_to:
        return False
    return True


def find_version(versions: Sequence[PolicyVersion], on: date) -> Optional[PolicyVersion]:
    for version in versions:
        if is_in_force(version, on):
            return version
    return None


def latest_version(versions: Sequence[PolicyVersion]) -> PolicyVersion:
    return max(versions, key=lambda v: (v.effective_from, v.version_id))


def select_version(versions: Sequence[PolicyVersion], policy_id: str, received_date: date) -> PolicyVersion:
    if not versions:
        raise LookupError(f"policy {policy_id} has no versions")
    version = find_version(versions, received_date)
    if version is None:
        version = latest_version(versions)
        log.warning(
            "no policy version of %s in force on received_date %s, falling back to latest (%s)",
            policy_id, received_date.isoformat(), version.version_id,
        )
    return version
