"""LNTRAN loading and payment application (1300-LOAD-TRANSACTIONS / 3100-APPLY-PAYMENTS)."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from .dates import from_yymmdd
from .layouts import LNTRAN
from .models import Transaction
from .numeric import ZERO, fit_pic

PAYMENT = "P"
REVERSAL = "R"
VOIDED = "V"


def load_transactions(path: str | Path) -> list[Transaction]:
    data = Path(path).read_bytes()
    out: list[Transaction] = []
    for raw in LNTRAN.read_records(data):
        rec = LNTRAN.decode(raw)
        out.append(
            Transaction(
                account=int(rec["TR-ACCT-NO"]),
                post_date=from_yymmdd(rec["TR-POST-DATE"]),
                seq=int(rec["TR-SEQ-NO"]),
                tran_type=rec["TR-TYPE"],
                amount=rec["TR-AMOUNT"],
                voided=rec["TR-VOID-FLAG"] == VOIDED,
                channel=rec["TR-CHANNEL"],
            )
        )
    # the capture file is in arrival order; the batch processes in posting order
    out.sort(key=lambda t: (t.account, t.post_date, t.seq))
    return out


def group_by_account(transactions: list[Transaction]) -> dict[int, list[Transaction]]:
    grouped: dict[int, list[Transaction]] = defaultdict(list)
    for t in transactions:
        grouped[t.account].append(t)
    return grouped


def paid_in_period(transactions: list[Transaction]) -> Decimal:
    """Net amount paid: payments less reversals, voided entries ignored (WS-PAID-AMT PIC S9(11)V99)."""
    total = ZERO
    for t in transactions:
        if t.voided:
            continue
        if t.tran_type == PAYMENT:
            total = fit_pic(total + t.amount, "S9(11)V99")
        elif t.tran_type == REVERSAL:
            total = fit_pic(total - t.amount, "S9(11)V99")
        else:
            raise ValueError(f"unknown transaction type {t.tran_type!r} on account {t.account}")
    return total


def apply_payments(principal: Decimal, paid: Decimal) -> Decimal:
    """WS-NEW-BAL = LM-PRIN-BAL - WS-PAID-AMT (may go negative: credit balance)."""
    return fit_pic(principal - paid, "S9(11)V99")
