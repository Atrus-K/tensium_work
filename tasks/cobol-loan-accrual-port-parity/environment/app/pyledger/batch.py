"""Batch orchestration: the Python counterpart of LNACCR01's PROCEDURE DIVISION.

    read LNMAST -> apply LNTRAN -> find tier -> accrue -> days late -> late fee
    -> status -> write LNOUT detail; closed accounts are skipped before any of
    it; the trailer carries count / hash / money totals over written records.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .accrual import accrue
from .dates import BusinessCalendar, from_yymmdd
from .fees import days_late, late_fee
from .layouts import LNMAST
from .models import Account, AccountResult, BatchTotals
from .numeric import ZERO, fit_pic
from .rates import RateTable
from .status import status_letter
from .transactions import apply_payments, group_by_account, load_transactions, paid_in_period
from .writer import LnoutWriter

log = logging.getLogger("pyledger.batch")

HASH_MODULUS = 10 ** 11  # LT-HASH-TOTAL PIC 9(11)
TOT_ACCRUED_PIC = "S9(11)V99"
TOT_FEES_PIC = "9(11)V99"
TOT_BALANCE_PIC = "S9(13)V99"


@dataclass
class BatchInputs:
    master: Path
    transactions: Path
    rates: Path
    holidays: Path
    asof: date
    output: Path


def load_master(path: str | Path) -> list[Account]:
    data = Path(path).read_bytes()
    accounts: list[Account] = []
    for raw in LNMAST.read_records(data):
        rec = LNMAST.decode(raw)
        accounts.append(
            Account(
                account=int(rec["LM-ACCT-NO"]),
                name=rec["LM-CUST-NAME"].rstrip(),
                product=rec["LM-PRODUCT-CD"],
                status=rec["LM-STATUS"],
                orig_date=from_yymmdd(rec["LM-ORIG-DATE"]),
                due_date=from_yymmdd(rec["LM-DUE-DATE"]),
                last_accrual_date=from_yymmdd(rec["LM-LAST-ACCR-DATE"]),
                principal=rec["LM-PRIN-BAL"],
                payment_due=rec["LM-PMT-DUE-AMT"],
                grace_days=int(rec["LM-GRACE-DAYS"]),
                branch=rec["LM-BRANCH-CD"],
                officer=rec["LM-OFFICER-ID"].rstrip(),
            )
        )
    return accounts


def process_account(account: Account, paid, rates: RateTable, calendar: BusinessCalendar, asof: date) -> AccountResult:
    new_balance = apply_payments(account.principal, paid)
    tier = rates.find_tier(new_balance)
    rate, days, interest = accrue(new_balance, tier, account.product, account.last_accrual_date, asof)
    late = days_late(account, paid, asof, calendar)
    fee = late_fee(account, tier, late, asof)
    letter = status_letter(late, account.grace_days)
    return AccountResult(
        account=account,
        new_balance=new_balance,
        paid_amount=paid,
        tier=tier,
        daily_rate=rate,
        accrual_days=days,
        accrued_interest=interest,
        days_late=late,
        late_fee=fee,
        status_letter=letter,
    )


def accumulate(totals: BatchTotals, result: AccountResult) -> None:
    totals.record_count += 1
    totals.hash_total = (totals.hash_total + result.account.account) % HASH_MODULUS
    totals.total_accrued = fit_pic(totals.total_accrued + result.accrued_interest, TOT_ACCRUED_PIC)
    totals.total_fees = fit_pic(totals.total_fees + result.late_fee, TOT_FEES_PIC)
    totals.total_balance = fit_pic(totals.total_balance + result.new_balance, TOT_BALANCE_PIC)


def run_batch(inputs: BatchInputs) -> BatchTotals:
    calendar = BusinessCalendar.load(inputs.holidays)
    rates = RateTable.load(inputs.rates)
    transactions = group_by_account(load_transactions(inputs.transactions))
    accounts = load_master(inputs.master)
    log.info("LNACCR01 as-of %s: %d master records, %d tiers", inputs.asof, len(accounts), len(rates.tiers))

    totals = BatchTotals()
    with LnoutWriter(inputs.output) as out:
        for account in accounts:
            if account.is_closed:
                totals.skipped_closed += 1
                continue
            paid = paid_in_period(transactions.get(account.account, []))
            result = process_account(account, paid, rates, calendar, inputs.asof)
            out.write_detail(result, inputs.asof)
            accumulate(totals, result)
            totals.results.append(result)
        out.write_trailer(totals)
    log.info("wrote %d detail records (+ trailer) to %s; %d closed accounts skipped",
             totals.record_count, inputs.output, totals.skipped_closed)
    return totals


__all__ = ["BatchInputs", "BatchTotals", "load_master", "process_account", "run_batch", "ZERO"]
