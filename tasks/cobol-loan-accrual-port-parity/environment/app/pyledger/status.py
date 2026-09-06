"""Delinquency status letter (3600-SET-STATUS).

Buckets: C current, L late, D delinquent (30+), X severely delinquent (60+),
W write-off referral (90+).
"""
from __future__ import annotations

STATUS_CURRENT = "C"
STATUS_LATE = "L"
STATUS_DELINQUENT = "D"
STATUS_SEVERE = "X"
STATUS_WRITEOFF = "W"


def status_letter(days_late: int, grace_days: int) -> str:
    if days_late == 0:
        return STATUS_CURRENT
    if days_late >= 90:
        return STATUS_WRITEOFF
    if days_late >= 60:
        return STATUS_SEVERE
    if days_late >= 30:
        return STATUS_DELINQUENT
    return STATUS_LATE
