"""Delinquency status letter (3600-SET-STATUS).

    EVALUATE TRUE
        WHEN WS-DAYS-LATE > 90              MOVE 'W' TO LO-STATUS   (write-off referral)
        WHEN WS-DAYS-LATE > 60              MOVE 'X' TO LO-STATUS   (severely delinquent)
        WHEN WS-DAYS-LATE > 30              MOVE 'D' TO LO-STATUS   (delinquent)
        WHEN WS-DAYS-LATE > LM-GRACE-DAYS   MOVE 'L' TO LO-STATUS   (late, past grace)
        WHEN OTHER                          MOVE 'C' TO LO-STATUS   (current)
    END-EVALUATE

EVALUATE takes the first WHEN that is true, so the thresholds are tested from the
most severe downwards and every comparison is strict.
"""
from __future__ import annotations

STATUS_CURRENT = "C"
STATUS_LATE = "L"
STATUS_DELINQUENT = "D"
STATUS_SEVERE = "X"
STATUS_WRITEOFF = "W"

LADDER = (
    (90, STATUS_WRITEOFF),
    (60, STATUS_SEVERE),
    (30, STATUS_DELINQUENT),
)


def status_letter(days_late: int, grace_days: int) -> str:
    for threshold, letter in LADDER:
        if days_late > threshold:
            return letter
    if days_late > grace_days:
        return STATUS_LATE
    return STATUS_CURRENT
