"""Control-total invariants of the LNOUT trailer, checked against the detail records actually written."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from conftest import MasterRow, Tier, unsigned_to_decimal, zoned_to_decimal


def _check_trailer(out):
    details = [out.details[a] for a in out.order]
    assert unsigned_to_decimal(out.trailer_field("REC_COUNT"), 0) == len(details)
    hash_total = sum(int(out.field(a, "ACCT_NO")) for a in out.order) % 10 ** 11
    assert unsigned_to_decimal(out.trailer_field("HASH_TOTAL"), 0) == hash_total
    tot_accrued = sum((zoned_to_decimal(out.field(a, "ACCRUED_INT"), 2) for a in out.order), Decimal(0))
    tot_fees = sum((unsigned_to_decimal(out.field(a, "LATE_FEE"), 2) for a in out.order), Decimal(0))
    tot_balance = sum((zoned_to_decimal(out.field(a, "BALANCE"), 2) for a in out.order), Decimal(0))
    assert zoned_to_decimal(out.trailer_field("TOT_ACCRUED"), 2) == tot_accrued
    assert unsigned_to_decimal(out.trailer_field("TOT_FEES"), 2) == tot_fees
    assert zoned_to_decimal(out.trailer_field("TOT_BALANCE"), 2) == tot_balance
    assert out.trailer_field("REC_TYPE") == "T"
    assert out.trailer_field("FILLER_1") == " " * 11 and out.trailer_field("FILLER_2") == " " * 9
    # every detail is a well-formed record of the copybook
    for a in out.order:
        assert out.field(a, "REC_TYPE") == "D"
        assert out.field(a, "FILLER") == " " * 9
        assert out.field(a, "STATUS") in "CLDXW"
        assert out.field(a, "DAYS_LATE").isdigit() and out.field(a, "LATE_FEE").isdigit()
        assert out.field(a, "DAILY_RATE").isdigit() and out.field(a, "ACCR_DAYS").isdigit()
        zoned_to_decimal(out.field(a, "BALANCE"), 2)
        zoned_to_decimal(out.field(a, "ACCRUED_INT"), 2)


def test_trailer_consistent_with_details_march(march_output):
    _check_trailer(march_output)


def test_trailer_consistent_with_details_may(may_output):
    _check_trailer(may_output)


def test_hash_total_wraps_modulo_10_to_the_11(mini):
    """Twelve accounts near 10^10 push the raw sum past 10^11; LT-HASH-TOTAL is PIC 9(11)."""
    accts = [9999999900 + i for i in range(12)]
    for a in accts:
        mini.add(MasterRow(acct=a, principal="100.00", payment_due="0.00", due=date(2024, 4, 15)))
    out = mini.run("2024-03-31")
    assert len(out.order) == 12
    assert out.trailer_field("REC_COUNT") == "0000012"
    expected = sum(accts) % 10 ** 11
    assert out.trailer_field("HASH_TOTAL") == f"{expected:011d}"
    _check_trailer(out)


def test_trailer_totals_carry_sign_and_exclude_closed_accounts(mini):
    mini.add(
        MasterRow(acct=1, principal="-500.00", payment_due="0.00", due=date(2024, 4, 15)),
        MasterRow(acct=2, principal="-125.25", payment_due="0.00", due=date(2024, 4, 15)),
        MasterRow(acct=3, status="Z", principal="99999.00", payment_due="100.00", due=date(2024, 1, 5)),
        MasterRow(acct=4, principal="200.00", payment_due="0.00", due=date(2024, 4, 15)),
    )
    out = mini.run("2024-03-31")
    assert out.order == ["0000000001", "0000000002", "0000000004"], "closed (status Z) account must not be written"
    assert out.trailer_field("REC_COUNT") == "0000003"
    assert out.trailer_field("HASH_TOTAL") == f"{7:011d}"
    # -500.00 - 125.25 + 200.00 = -425.25 -> S9(13)V99 with negative overpunch on the 5
    assert out.trailer_field("TOT_BALANCE") == "00000000004252N"
    assert out.trailer_field("TOT_ACCRUED") == "000000000010D"  # credit balances accrue nothing; 200.00 * 0.000167808 * 31 = 1.04
    _check_trailer(out)


def test_trailer_accrued_total_is_exact_decimal_sum(mini):
    """Many small accruals: the trailer must equal the exact sum of the written cents, not a float sum."""
    mini.tiers = [Tier("99999999999.99", "0.07250", "0.0500", "15.00", "50.00")]
    for i in range(1, 61):
        mini.add(MasterRow(acct=i, product="P", principal=f"{i * 37 + 0.33:.2f}", payment_due="0.00",
                           due=date(2024, 4, 15), last_accr=date(2024, 2, 29)))
    out = mini.run("2024-03-31")
    assert len(out.order) == 60
    _check_trailer(out)
    with pytest.raises(AssertionError):
        # sanity: the helper really compares (a wrong trailer would be caught)
        broken = type(out)(details=out.details, order=out.order, trailer=out.trailer[:18] + "9" + out.trailer[19:], raw=out.raw)
        _check_trailer(broken)
