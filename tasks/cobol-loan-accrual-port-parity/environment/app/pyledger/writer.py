"""LNOUT detail and trailer construction (3700-WRITE-DETAIL / 4000-WRITE-TRAILER)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import BinaryIO

from .dates import to_yyyymmdd
from .layouts import LNOUT_DETAIL, LNOUT_TRAILER, REC_TYPE_DETAIL, REC_TYPE_TRAILER
from .models import AccountResult, BatchTotals


def detail_record(result: AccountResult, asof: date) -> bytes:
    acct = result.account
    return LNOUT_DETAIL.encode(
        {
            "LO-ACCT-NO": Decimal(acct.account),
            "LO-PRODUCT-CD": acct.product,
            "LO-ASOF-DATE": Decimal(to_yyyymmdd(asof)),
            "LO-BALANCE": result.new_balance,
            "LO-ACCRUED-INT": result.accrued_interest,
            "LO-LATE-FEE": result.late_fee,
            "LO-DAYS-LATE": Decimal(result.days_late),
            "LO-STATUS": result.status_letter,
            "LO-RATE-TIER": Decimal(result.tier.index),
            "LO-DAILY-RATE": result.daily_rate,
            "LO-ACCR-DAYS": Decimal(result.accrual_days),
            "LO-REC-TYPE": REC_TYPE_DETAIL,
            "FILLER": "",
        }
    )


def trailer_record(totals: BatchTotals) -> bytes:
    return LNOUT_TRAILER.encode(
        {
            "LT-REC-COUNT": Decimal(totals.record_count),
            "LT-HASH-TOTAL": Decimal(totals.hash_total),
            "LT-TOT-ACCRUED": totals.total_accrued,
            "LT-TOT-FEES": totals.total_fees,
            "LT-TOT-BALANCE": totals.total_balance,
            "FILLER-1": "",
            "LT-REC-TYPE": REC_TYPE_TRAILER,
            "FILLER-2": "",
        }
    )


class LnoutWriter:
    """Streams LNOUT records to a file; the trailer is written on close()."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh: BinaryIO | None = None
        self.records_written = 0

    def __enter__(self) -> "LnoutWriter":
        self._fh = open(self.path, "wb")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    def write_detail(self, result: AccountResult, asof: date) -> None:
        assert self._fh is not None
        self._fh.write(detail_record(result, asof))
        self.records_written += 1

    def write_trailer(self, totals: BatchTotals) -> None:
        assert self._fh is not None
        self._fh.write(trailer_record(totals))
