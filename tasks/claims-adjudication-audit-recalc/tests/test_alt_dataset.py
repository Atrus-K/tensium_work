"""Boundary cases on a second dataset (tests/fixtures/alt_dataset) with different
statute parameters, batch 2024-07 and payment date 2024-07-15."""
from __future__ import annotations

import json
from decimal import Decimal

import pytest

from conftest import D

# NOTE: keep in sync with tests/oracle.py whenever tests/fixtures/alt_dataset changes.
GOLDEN = {
    # Loss 2024-07-10 == PV-9001-B.effective_from -> B: deductible 2000, jewelry sublimit 2500.
    # jewelry 2000+900 = 2900 -> 2500 (-400); laptop 2400@18m 30% = 1680 -> gross 4580, covered 4180 - 2000 = 2180.
    # TX (alt): POL 07-11 + 7 bd = 07-22 -> not late.
    "CLM-24-0701": ("PV-9001-B", "paid", "4580.00", "400.00", "2000.00", "2180.00", 0, "0.00"),
    # Loss 2024-07-09, the day before the renewal -> A: deductible 1000, jewelry 1500 (watch 1700 -> 1500).
    "CLM-24-0702": ("PV-9001-A", "paid", "2720.00", "200.00", "1000.00", "1520.00", 0, "0.00"),
    # Loss 2024-07-05 == PV-9002-A.effective_to, never renewed -> no coverage.
    "CLM-24-0703": ("", "no_coverage", "0.00", "0.00", "0.00", "0.00", 0, "0.00"),
    # Loss 2024-07-04, last covered day of PV-9002-A. cabinets 3900@36m 30% = 2730; dishwasher 1200@54m 56.25% = 525.
    # CA (alt): FNOL 07-04 + 30 calendar = 08-03 -> not late.
    "CLM-24-0704": ("PV-9002-A", "paid", "3255.00", "0.00", "1500.00", "1755.00", 0, "0.00"),
    # Supplemental on OCC-24-0322: jewelry headroom 0 (1500 used), electronics headroom 4000-2400 = 1600,
    # deductible absorbed by the original. earrings 500 -> 0; monitor 2000@6m 10% = 1800 -> 1600; coats 800@5m = 800.
    # gross 3100, reduction 700, deductible 0 -> 2400. FL (alt): POL 06-28 + 14 calendar = 07-12 -> 3 days;
    # 2400*.10*3/365 = 1.9726 -> 1.97
    "CLM-24-0705": ("PV-9003-A", "paid", "3100.00", "700.00", "0.00", "2400.00", 3, "1.97"),
    # OH: 800+950+750 = 2500 gross, deductible 3000 -> zero payment absorbing 2500.
    # OH (alt): POL Mon 06-24 + 5 bd = 07-01 -> 14 days late, but interest never applies.
    "CLM-24-0706": ("PV-9004-A", "zero_payment", "2500.00", "0.00", "2500.00", "0.00", 14, "0.00"),
    # Same occurrence, later in the same batch: remaining deductible 500. camera 1500@24m 40% = 900; chest 800@18m 15% = 680.
    "CLM-24-0707": ("PV-9004-A", "paid", "1580.00", "0.00", "500.00", "1080.00", 0, "0.00"),
    # Supplemental exhausting the limit: 24000 - 22250 already paid = 1750 headroom (gross 2400+300 = 2700, no deductible).
    # NY (alt): FNOL Thu 06-20 + 12 bd (07-04 skipped) = 07-09 -> 6 days; 1750*.09*6/365 = 2.589 -> 2.59
    "CLM-24-0708": ("PV-9005-A", "paid", "2700.00", "0.00", "0.00", "1750.00", 6, "2.59"),
    # Age threshold: bookshelf bought 2023-12-25, loss 2024-06-25 -> exactly 6 months -> 5% -> 760;
    # lamp bought 2023-12-26 -> 5 months -> 300; router 240@12m 20% = 192; textbooks 1000@60m cap 80% = 200; sofa 3000@24m = 2400.
    # gross 3852 - 1500 = 2352. TX (alt): POL Mon 07-01 + 7 bd (07-04 skipped) = 07-11 -> 4 days; 2352*.15*4/365 = 3.866 -> 3.87
    "CLM-24-0709": ("PV-9006-A", "paid", "3852.00", "0.00", "1500.00", "2352.00", 4, "3.87"),
    # Wind on PV-9001-B (2% of 400000 = 8000): 7200 + 1700 + 1000 = 9900 - 8000 = 1900.
    "CLM-24-0710": ("PV-9001-B", "paid", "9900.00", "0.00", "8000.00", "1900.00", 0, "0.00"),
    # Hail on a version with no wind/hail pct -> flat 1500. TX (alt): POL Wed 07-03 + 7 bd = 07-15 -> not late.
    "CLM-24-0711": ("PV-9006-A", "paid", "4600.00", "0.00", "1500.00", "3100.00", 0, "0.00"),
    # Electronics aggregate 4050 + 1500 = 5550 -> sublimit 4000 (-1550); sofa 1600 -> covered 5600 - 1000 = 4600.
    # FL (alt): POL 06-20 + 14 calendar = 07-04 -> 11 days; 4600*.10*11/365 = 13.863 -> 13.86
    "CLM-24-0712": ("PV-9003-A", "paid", "7150.00", "1550.00", "1000.00", "4600.00", 11, "13.86"),
    # OH late by 14 days, interest_applies false.
    "CLM-24-0713": ("PV-9004-A", "paid", "5500.00", "0.00", "3000.00", "2500.00", 14, "0.00"),
    # NY (alt) FNOL Mon 06-24 + 12 bd (07-04 skipped) = 07-11 -> 4 days; 1100*.09*4/365 = 1.0849 -> 1.08
    "CLM-24-0714": ("PV-9005-A", "paid", "2100.00", "0.00", "1000.00", "1100.00", 4, "1.08"),
    # OCC-24-0715, both claims in the batch with the same loss date but received in the REVERSE of claim-id order:
    # CLM-24-0716 (received 07-06) is processed before CLM-24-0715 (received 07-11), so 0716 absorbs the 1200 deductible.
    # 0716: television 1500@12m 20% = 1200; armchair 500@4m = 500 -> gross 1700 - 1200 = 500. CA: FNOL 07-03 + 30 = 08-02.
    "CLM-24-0716": ("PV-9007-A", "paid", "1700.00", "0.00", "1200.00", "500.00", 0, "0.00"),
    # 0715: necklace 1000 (jewelry, within 1500); sofa 2400@24m 20% = 1920 -> gross 2920, deductible already absorbed -> 2920.
    "CLM-24-0715": ("PV-9007-A", "paid", "2920.00", "0.00", "0.00", "2920.00", 0, "0.00"),
}


@pytest.mark.parametrize("claim_id", sorted(GOLDEN), ids=sorted(GOLDEN))
def test_alt_boundary_case(alt_run, claim_id):
    version, status, gross, reduction, ded, indemnity, days_late, interest = GOLDEN[claim_id]
    row = alt_run.rows[claim_id]
    assert row["policy_version_id"] == version
    assert row["status"] == status
    assert D(row["gross_acv"]) == D(gross)
    assert D(row["sublimit_reduction"]) == D(reduction)
    assert D(row["deductible_applied"]) == D(ded)
    assert D(row["indemnity"]) == D(indemnity)
    assert int(row["days_late"]) == days_late
    assert D(row["interest"]) == D(interest)


def test_zero_payment_claim_still_records_deductible_absorbed(alt_run):
    pays = alt_run.payments_for_claim("CLM-24-0706")
    assert len(pays) == 1
    assert D(pays[0]["indemnity"]) == 0
    assert D(pays[0]["deductible_applied"]) == D("2500.00")


def test_supplemental_sees_original_in_same_batch(alt_run):
    occ = alt_run.payments_for_occurrence("OCC-24-0706")
    assert sum(D(p["deductible_applied"]) for p in occ) == D("3000.00")  # 2500 + 500 = the occurrence deductible, once


def test_processing_order_is_loss_date_then_received_date_not_claim_id(alt_run):
    """CH-7 section 2 / 8: within an occurrence the claim received earlier counts as prior activity,
    even when its claim id sorts later."""
    first = alt_run.payments_for_claim("CLM-24-0716")
    second = alt_run.payments_for_claim("CLM-24-0715")
    assert len(first) == 1 and len(second) == 1
    assert D(first[0]["deductible_applied"]) == D("1200.00")
    assert D(second[0]["deductible_applied"]) == 0
    assert sum(D(p["deductible_applied"]) for p in alt_run.payments_for_occurrence("OCC-24-0715")) == D("1200.00")
