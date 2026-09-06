"""Mini-batches that each isolate one clause of LNACCR01.cbl / the copybooks.

Expected values are derived by hand from the COBOL text (PIC scales, ROUNDED,
INTEGER-OF-DATE arithmetic, 2000-CENTURY-WINDOW, 2300-DAYS-360, 3500-ASSESS-LATE-FEE,
3600-SET-STATUS) and compared as the raw fixed-width field text the mainframe writes.
"""
from __future__ import annotations

from datetime import date

from conftest import MARCH_TIERS, MasterRow, Tier, TranRow

ASOF = "2024-03-31"  # a Sunday; INTEGER-OF-DATE differences are exclusive


# ------------------------------------------------------------------ numeric semantics

def test_accrued_interest_rounds_half_away_from_zero(mini):
    mini.tiers = [Tier("5000.00", "0.06750", "0.0450", "20.00", "75.00"),
                  Tier("99999999999.99", "0.06125", "0.0400", "25.00", "150.00")]
    mini.add(
        # tier 1: 0.06750 / 360 = 0.0001875 exactly; 1187.50 * 0.0001875 * 32 = 7.125 -> ROUNDED -> 7.13
        MasterRow(acct=1, product="M", principal="1187.50", payment_due="0.00", last_accr=date(2024, 2, 29)),
        # tier 2: 0.06125 / 365 -> 0.000167808; 39062.50 * 0.000167808 * 31 = 203.205 -> 203.21
        MasterRow(acct=2, product="A", principal="39062.50", payment_due="0.00", last_accr=date(2024, 2, 29)),
    )
    out = mini.run(ASOF)
    assert out.field("0000000001", "DAILY_RATE") == "0000187500"
    assert out.field("0000000001", "ACCR_DAYS") == "032"
    assert out.field("0000000001", "ACCRUED_INT") == "0000000071C"
    assert out.field("0000000002", "DAILY_RATE") == "0000167808"
    assert out.field("0000000002", "ACCR_DAYS") == "031"
    assert out.field("0000000002", "ACCRUED_INT") == "0000002032A"


def test_daily_rate_is_truncated_to_nine_decimals_before_multiplying(mini):
    # 0.07250 / 360 = 0.000201388 88.. -> WS-DAILY-RATE PIC 9V9(9) (no ROUNDED) = 0.000201388
    # 250000.00 * 0.000201388 * 32 = 1611.104 -> 1611.10   (a rounded rate would give 1611.11)
    mini.tiers = [Tier("99999999999.99", "0.07250", "0.0500", "15.00", "50.00")]
    mini.add(MasterRow(acct=7, product="M", principal="250000.00", payment_due="0.00", last_accr=date(2024, 2, 29)))
    out = mini.run(ASOF)
    assert out.field("0000000007", "DAILY_RATE") == "0000201388"
    assert out.field("0000000007", "ACCR_DAYS") == "032"
    assert out.field("0000000007", "ACCRUED_INT") == "0000016111{"


def test_late_fee_rounding_and_tier_caps(mini):
    mini.tiers = [Tier("99999999999.99", "0.06750", "0.0450", "20.00", "75.00")]
    due = date(2024, 3, 1)  # Friday, 30 days before as-of; grace 10 -> fee applies
    mini.add(
        MasterRow(acct=1, due=due, payment_due="445.00"),   # 445.00 * 0.045 = 20.025 -> 20.03 (half up)
        MasterRow(acct=2, due=due, payment_due="2000.00"),  # 90.00 -> capped at 75.00
        MasterRow(acct=3, due=due, payment_due="100.00"),   # 4.50 -> floored at 20.00
    )
    out = mini.run(ASOF)
    assert out.field("0000000001", "LATE_FEE") == "000002003"
    assert out.field("0000000002", "LATE_FEE") == "000007500"
    assert out.field("0000000003", "LATE_FEE") == "000002000"
    for a in ("0000000001", "0000000002", "0000000003"):
        assert out.field(a, "DAYS_LATE") == "030" and out.field(a, "STATUS") == "L"


# ------------------------------------------------------------------ zoned decimal signs

def test_negative_master_balance_round_trips_with_negative_overpunch(mini):
    mini.add(MasterRow(acct=5, principal="-123.45", payment_due="0.00"))
    out = mini.run(ASOF)
    assert out.field("0000000005", "BALANCE") == "000000001234N"
    assert out.field("0000000005", "ACCRUED_INT") == "0000000000{"  # no interest on a credit balance
    assert out.field("0000000005", "DAYS_LATE") == "000" and out.field("0000000005", "STATUS") == "C"
    assert out.field("0000000005", "RATE_TIER") == "1"


def test_overpayment_produces_credit_balance(mini):
    mini.add(MasterRow(acct=6, principal="1000.00", payment_due="100.00", due=date(2024, 3, 1)))
    mini.pay(TranRow(6, date(2024, 3, 4), 1, "P", "1250.00"))
    out = mini.run(ASOF)
    assert out.field("0000000006", "BALANCE") == "000000002500}"  # -250.00
    assert out.field("0000000006", "ACCRUED_INT") == "0000000000{"
    assert out.field("0000000006", "DAYS_LATE") == "000"
    assert out.field("0000000006", "LATE_FEE") == "000000000"


def test_negative_transaction_amount_is_a_correction(mini):
    # LNTRAN.cpy: a negative 'P' amount reduces the amount paid (and so raises the balance)
    mini.add(MasterRow(acct=8, principal="1000.00", payment_due="100.00", due=date(2024, 3, 1), grace=10))
    mini.pay(TranRow(8, date(2024, 3, 12), 1, "P", "-50.00"))
    out = mini.run(ASOF)
    assert out.field("0000000008", "BALANCE") == "000000010500{"  # 1000.00 + 50.00
    assert out.field("0000000008", "ACCRUED_INT") == "0000000054F"  # 1050 * 0.000167808 * 31 = 5.46215 -> 5.46
    assert out.field("0000000008", "DAYS_LATE") == "030"
    assert out.field("0000000008", "STATUS") == "L"
    assert out.field("0000000008", "LATE_FEE") == "000002500"  # 100 * 0.04 = 4.00 -> min 25.00


# ------------------------------------------------------------------ dates

def test_two_digit_year_century_window_for_origination(mini):
    due = date(2024, 3, 1)  # 30 days late, grace 10, payment 200.00 -> 8.00 -> min 25.00 when charged
    mini.add(
        MasterRow(acct=1, due=due, payment_due="200.00", orig=date(1998, 5, 12)),   # YY 98 -> 1998: fee
        MasterRow(acct=2, due=due, payment_due="200.00", orig=date(2024, 1, 1)),    # age 90: courtesy window
        MasterRow(acct=3, due=due, payment_due="200.00", orig=date(2023, 12, 31)),  # age 91: fee
        MasterRow(acct=4, due=due, payment_due="200.00", orig=date(1950, 1, 1)),    # YY 50 -> 1950: fee
    )
    out = mini.run(ASOF)
    assert out.field("0000000001", "LATE_FEE") == "000002500"
    assert out.field("0000000002", "LATE_FEE") == "000000000"
    assert out.field("0000000003", "LATE_FEE") == "000002500"
    assert out.field("0000000004", "LATE_FEE") == "000002500"
    for a in ("0000000001", "0000000002", "0000000003", "0000000004"):
        assert out.field(a, "STATUS") == "L" and out.field(a, "DAYS_LATE") == "030"


def test_30_360_day_count_applies_both_end_of_month_clamps(mini):
    mini.tiers = [Tier("99999999999.99", "0.07250", "0.0500", "15.00", "50.00")]
    mini.add(
        MasterRow(acct=1, product="M", payment_due="0.00", last_accr=date(2024, 1, 31)),  # D1 31->30, D2 31->30: 60
        MasterRow(acct=2, product="M", payment_due="0.00", last_accr=date(2024, 1, 30)),  # D1 30, D2 31->30: 60
        MasterRow(acct=3, product="M", payment_due="0.00", last_accr=date(2024, 1, 29)),  # D2 stays 31: 62
        MasterRow(acct=4, product="M", payment_due="0.00", last_accr=date(2024, 2, 29)),  # 32
        MasterRow(acct=5, product="M", payment_due="0.00", last_accr=date(2024, 1, 15)),  # 76
        MasterRow(acct=6, product="A", payment_due="0.00", last_accr=date(2024, 1, 31)),  # actual: 60
        MasterRow(acct=7, product="P", payment_due="0.00", last_accr=date(2024, 1, 30)),  # actual: 61
    )
    out = mini.run(ASOF)
    expected = {"1": "060", "2": "060", "3": "062", "4": "032", "5": "076", "6": "060", "7": "061"}
    for k, days in expected.items():
        assert out.field(f"{int(k):010d}", "ACCR_DAYS") == days, f"account {k}"
    assert out.field("0000000001", "DAILY_RATE") == "0000201388"  # /360
    assert out.field("0000000006", "DAILY_RATE") == "0000198630"  # 0.07250/365 = 0.000198630 13..


def test_days_late_is_exclusive_from_rolled_due_date_and_grace_is_strict(mini):
    grace = 5
    mini.add(
        MasterRow(acct=1, due=date(2024, 3, 26), grace=grace, payment_due="300.00"),  # Tue: 5 days = grace
        MasterRow(acct=2, due=date(2024, 3, 25), grace=grace, payment_due="300.00"),  # Mon: 6 days
        MasterRow(acct=3, due=date(2024, 3, 23), grace=grace, payment_due="300.00"),  # Sat -> Mon 25th: 6 days
        MasterRow(acct=4, due=date(2024, 2, 17), grace=grace, payment_due="300.00"),  # Sat -> Mon 19th holiday -> 20th: 40
        MasterRow(acct=5, due=date(2024, 4, 1), grace=grace, payment_due="300.00"),   # not yet due
        MasterRow(acct=6, due=date(2024, 3, 31), grace=grace, payment_due="300.00"),  # Sun -> Mon Apr 1: not yet due
    )
    out = mini.run(ASOF)
    assert (out.field("0000000001", "DAYS_LATE"), out.field("0000000001", "LATE_FEE"), out.field("0000000001", "STATUS")) == ("005", "000000000", "C")
    assert (out.field("0000000002", "DAYS_LATE"), out.field("0000000002", "LATE_FEE"), out.field("0000000002", "STATUS")) == ("006", "000002500", "L")
    assert (out.field("0000000003", "DAYS_LATE"), out.field("0000000003", "STATUS")) == ("006", "L")
    assert (out.field("0000000004", "DAYS_LATE"), out.field("0000000004", "STATUS")) == ("040", "D")
    assert (out.field("0000000005", "DAYS_LATE"), out.field("0000000005", "STATUS")) == ("000", "C")
    assert (out.field("0000000006", "DAYS_LATE"), out.field("0000000006", "STATUS")) == ("000", "C")


def test_paid_in_full_uses_net_payments_and_ignores_voids(mini):
    due = date(2024, 3, 1)
    mini.add(
        MasterRow(acct=1, due=due, payment_due="300.00"),  # two payments sum to exactly the amount due
        MasterRow(acct=2, due=due, payment_due="300.00"),  # one cent short
        MasterRow(acct=3, due=due, payment_due="300.00"),  # paid then reversed
        MasterRow(acct=4, due=due, payment_due="300.00"),  # voided payment
        MasterRow(acct=5, due=due, payment_due="300.00"),  # overpaid
    )
    mini.pay(
        TranRow(1, date(2024, 3, 20), 2, "P", "150.00"), TranRow(1, date(2024, 3, 5), 1, "P", "150.00"),
        TranRow(2, date(2024, 3, 5), 1, "P", "150.00"), TranRow(2, date(2024, 3, 20), 2, "P", "149.99"),
        TranRow(3, date(2024, 3, 5), 1, "P", "300.00"), TranRow(3, date(2024, 3, 8), 2, "R", "300.00"),
        TranRow(4, date(2024, 3, 5), 1, "P", "300.00", void="V"),
        TranRow(5, date(2024, 3, 5), 1, "P", "400.00"),
    )
    out = mini.run(ASOF)
    assert out.field("0000000001", "DAYS_LATE") == "000" and out.field("0000000001", "STATUS") == "C"
    assert out.field("0000000002", "DAYS_LATE") == "030" and out.field("0000000002", "STATUS") == "L"
    assert out.field("0000000003", "DAYS_LATE") == "030" and out.field("0000000003", "BALANCE") == "000000100000{"
    assert out.field("0000000004", "DAYS_LATE") == "030" and out.field("0000000004", "BALANCE") == "000000100000{"
    assert out.field("0000000005", "DAYS_LATE") == "000" and out.field("0000000005", "BALANCE") == "000000096000{"
    assert out.field("0000000001", "BALANCE") == "000000097000{"


# ------------------------------------------------------------------ copybook v3 flag

def test_waive_flag_from_lnmast_v3_suppresses_the_fee_but_not_the_status(mini):
    due = date(2024, 3, 1)
    mini.add(
        MasterRow(acct=1, due=due, payment_due="300.00", waive="Y"),
        MasterRow(acct=2, due=due, payment_due="300.00", waive=" "),
        MasterRow(acct=3, due=due, payment_due="300.00", waive="N"),
    )
    out = mini.run(ASOF)
    assert out.field("0000000001", "LATE_FEE") == "000000000"
    assert out.field("0000000002", "LATE_FEE") == "000002500"
    assert out.field("0000000003", "LATE_FEE") == "000002500"
    for a in ("0000000001", "0000000002", "0000000003"):
        assert out.field(a, "DAYS_LATE") == "030" and out.field(a, "STATUS") == "L"


# ------------------------------------------------------------------ tiers

def test_tier_upper_bound_is_inclusive_and_tier_code_is_one_based(mini):
    mini.tiers = list(MARCH_TIERS)
    mini.add(
        MasterRow(acct=1, principal="5000.00", payment_due="0.00"),
        MasterRow(acct=2, principal="5000.01", payment_due="0.00"),
        MasterRow(acct=3, principal="25000.00", payment_due="0.00"),
        MasterRow(acct=4, principal="100000.00", payment_due="0.00"),
        MasterRow(acct=5, principal="250000.01", payment_due="0.00"),
        MasterRow(acct=6, principal="-40.00", payment_due="0.00"),
    )
    out = mini.run(ASOF)
    tiers = {a: out.field(f"{a:010d}", "RATE_TIER") for a in range(1, 7)}
    assert tiers == {1: "1", 2: "2", 3: "2", 4: "3", 5: "5", 6: "1"}
    assert out.field("0000000001", "DAILY_RATE") == "0000198630"  # 0.07250/365
    assert out.field("0000000002", "DAILY_RATE") == "0000184931"  # 0.06750/365 = 0.000184931 50..
    assert out.field("0000000004", "DAILY_RATE") == "0000167808"  # 0.06125/365
    assert out.field("0000000005", "DAILY_RATE") == "0000133561"  # 0.04875/365 = 0.000133561 64..


# ------------------------------------------------------------------ status ladder

def test_status_ladder_thresholds_are_strict_first_match(mini):
    grace = 5
    mini.add(
        MasterRow(acct=1, due=date(2024, 3, 28), grace=grace, payment_due="100.00"),  # 3 days: within grace
        MasterRow(acct=2, due=date(2024, 3, 26), grace=grace, payment_due="100.00"),  # 5 = grace
        MasterRow(acct=3, due=date(2024, 3, 25), grace=grace, payment_due="100.00"),  # 6
        MasterRow(acct=4, due=date(2024, 3, 1), grace=grace, payment_due="100.00"),   # 30
        MasterRow(acct=5, due=date(2024, 2, 29), grace=grace, payment_due="100.00"),  # 31
        MasterRow(acct=6, due=date(2024, 1, 31), grace=grace, payment_due="100.00"),  # 60
        MasterRow(acct=7, due=date(2024, 1, 30), grace=grace, payment_due="100.00"),  # 61
        MasterRow(acct=8, due=date(2024, 3, 28), grace=0, payment_due="100.00"),      # 3 days, no grace
    )
    out = mini.run(ASOF)
    got = {a: (out.field(f"{a:010d}", "DAYS_LATE"), out.field(f"{a:010d}", "STATUS")) for a in range(1, 9)}
    assert got == {
        1: ("003", "C"), 2: ("005", "C"), 3: ("006", "L"), 4: ("030", "L"),
        5: ("031", "D"), 6: ("060", "D"), 7: ("061", "X"), 8: ("003", "L"),
    }


def test_status_ladder_at_ninety_days(mini):
    mini.add(
        MasterRow(acct=1, due=date(2024, 1, 31), grace=5, payment_due="100.00", last_accr=date(2024, 3, 31)),  # 90
        MasterRow(acct=2, due=date(2024, 1, 30), grace=5, payment_due="100.00", last_accr=date(2024, 3, 31)),  # 91
    )
    out = mini.run("2024-04-30")
    assert (out.field("0000000001", "DAYS_LATE"), out.field("0000000001", "STATUS")) == ("090", "X")
    assert (out.field("0000000002", "DAYS_LATE"), out.field("0000000002", "STATUS")) == ("091", "W")
    assert out.field("0000000001", "ASOF_DATE") == "20240430"


def test_days_late_high_order_digits_are_dropped_on_store(mini):
    """WS-DAYS-LATE is S9(5) and drives the status ladder; LO-DAYS-LATE is 9(3), so a MOVE of
    1034 writes '034' (ARITH(EXTEND) header: high-order digits that do not fit are dropped)."""
    mini.add(
        MasterRow(acct=1, due=date(2021, 6, 1), grace=10, payment_due="300.00"),             # Tue: 1034 days
        MasterRow(acct=2, due=date(2021, 7, 1), grace=10, payment_due="300.00"),             # Thu: 1004 days
        MasterRow(acct=3, due=date(2021, 7, 1), grace=10, payment_due="300.00", waive="Y"),
    )
    out = mini.run(ASOF)
    assert (out.field("0000000001", "DAYS_LATE"), out.field("0000000001", "STATUS")) == ("034", "W")
    assert (out.field("0000000002", "DAYS_LATE"), out.field("0000000002", "STATUS")) == ("004", "W")
    assert out.field("0000000001", "LATE_FEE") == "000002500"  # 300 * 0.04 = 12.00 -> min 25.00
    assert out.field("0000000002", "LATE_FEE") == "000002500"
    assert out.field("0000000003", "LATE_FEE") == "000000000" and out.field("0000000003", "STATUS") == "W"


# ------------------------------------------------------------------ record shape

def test_detail_record_shape_and_closed_accounts(mini):
    mini.add(
        MasterRow(acct=11, product="P", principal="1234.56", payment_due="0.00"),
        MasterRow(acct=12, status="Z", principal="9999.00", payment_due="10.00", due=date(2024, 1, 2)),
    )
    out = mini.run(ASOF)
    assert out.order == ["0000000011"]
    rec = out.details["0000000011"]
    assert len(rec) == 80
    assert rec[0:10] == "0000000011" and rec[10] == "P" and rec[11:19] == "20240331"
    assert out.field("0000000011", "BALANCE") == "000000012345F"
    assert out.field("0000000011", "REC_TYPE") == "D" and out.field("0000000011", "FILLER") == " " * 9
    assert out.trailer_field("REC_COUNT") == "0000001"
