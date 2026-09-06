"""Hand-derived figures for June claims the audit did NOT sample.

Each expectation is derived from docs/adjudication_rules.md; the derivation is
in the comment so a reviewer can re-check it without running anything.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import D

# claim_id -> (version, status, gross, sublimit_reduction, deductible_applied, indemnity, days_late, interest)
# NOTE: these hand-derived figures must be kept in sync with tests/oracle.py whenever the data files change;
# test_invariants recomputes every claim with the oracle, the goldens pin the derivations independently.
GOLDEN = {
    # Loss 2024-06-01 is exactly PV-1001-B.effective_from -> B (deductible 2500).
    # sofa 3200 @18m furniture 15% = 2720; TV 1800 @6m electronics 10% = 1620; books 950 @108m -> cap 80% = 190.
    # gross 4530 - 2500 = 2030. TX: POL Tue 06-04 + 5 bd = 06-11 -> 19 days; 2030*.18*19/365 = 19.018 -> 19.02
    "CLM-24-0602": ("PV-1001-B", "paid", "4530.00", "0.00", "2500.00", "2030.00", 19, "19.02"),
    # Loss 2024-04-30, the day before PV-1002-A lapsed -> covered even though received in June (rule 1.2).
    # bedroom set 4100 @36m 30% = 2870; washer 1290 purchased 2020-10-31 -> 41 whole months (30 < 31),
    # 12.5*41/12 = 42.7083% -> 1290*0.572916.. = 739.0625 -> 739.06. gross 3609.06 - 1000 = 2609.06.
    # TX: POL Wed 06-05 + 5 bd = 06-12 -> 18 days; 2609.06*.18*18/365 = 23.1596 -> 23.16
    "CLM-24-0616": ("PV-1002-A", "paid", "3609.06", "0.00", "1000.00", "2609.06", 18, "23.16"),
    # Loss 2024-03-20 falls in the lapse gap between PV-1016-A (to 03-01) and PV-1016-B (from 04-15).
    "CLM-24-0618": ("", "no_coverage", "0.00", "0.00", "0.00", "0.00", 0, "0.00"),
    # OH original: gross 880+560+360 = 1800 < deductible 2500 -> zero payment, absorbs 1800.
    "CLM-24-0614": ("PV-1014-A", "zero_payment", "1800.00", "0.00", "1800.00", "0.00", 12, "0.00"),
    # OH supplemental on the same occurrence, same batch: laptop 2000 @6m 10% = 1800; bicycle 500 @12m 15% = 425;
    # remaining deductible 2500-1800 = 700 -> 2225-700 = 1525. OH: FNOL Mon 06-17 + 10 bd (Juneteenth skipped) = 07-02 -> not late.
    "CLM-24-0615": ("PV-1014-A", "paid", "2225.00", "0.00", "700.00", "1525.00", 0, "0.00"),
    # Loss 2024-05-19 is the day before the 05-20 renewal -> PV-1018-A (wind/hail 2% of 360000 = 7200).
    # 9500@24m 20% = 7600; 3200@36m 60% = 1280; 4800@48m 12.5*4 = 50% = 2400 -> gross 11280 - 7200 = 4080.
    # FL: FNOL Sun 05-19 + 20 bd (Memorial Day skipped) = 06-17 -> 13 days; 4080*.12*13/365 = 17.437 -> 17.44
    "CLM-24-0622": ("PV-1018-A", "paid", "11280.00", "0.00", "7200.00", "4080.00", 13, "17.44"),
    # Half-cent lines: 100.30 @6m 5% = 95.285 -> 95.29; 200.20 @9m tools 7.5% = 185.185 -> 185.19;
    # 4300@48m 40% = 2580; 1700@18m 30% = 1190; 260@36m 60% = 104 -> gross 4154.48 - 1000 = 3154.48.
    # CA: POL 06-19 + 40 calendar = 07-29 -> not late.
    "CLM-24-0621": ("PV-1017-A", "paid", "4154.48", "0.00", "1000.00", "3154.48", 0, "0.00"),
    # Jewelry 1600+1400 = 3000 vs sublimit 2500 (-500); cash 500 vs 200 (-300); laptop 2200@15m 25% = 1650.
    # gross 5150, covered 4350, deductible 2500 -> 1850. NY: POL 06-12 + 30 = 07-12 -> not late.
    "CLM-24-0624": ("PV-1020-A", "paid", "5150.00", "800.00", "2500.00", "1850.00", 0, "0.00"),
    # Loss 05-25 falls in endorsement PV-1008-B (jewelry 2500, firearms 2500).
    # jewelry 1800+1200 = 3000 -> 2500 (-500); rifle 2100@30m 5*30/12 = 12.5% = 1837.50, shotgun 1300@6m (<12) = 1300
    # -> firearms 3137.50 -> 2500 (-637.50); gross 6137.50, covered 5000 - 1000 = 4000. OH: no interest.
    "CLM-24-0609": ("PV-1008-B", "paid", "6137.50", "1137.50", "1000.00", "4000.00", 20, "0.00"),
    # TX hail: 2% of 340000 = 6800. 9600@12m 10% = 8640; 1500@24m 40% = 900; 700@48m 60% = 280 -> 9820 - 6800 = 3020.
    # TX: POL Tue 06-18 + 5 bd (Juneteenth 06-19 skipped) = 06-26 -> 4 days; 3020*.18*4/365 = 5.957 -> 5.96
    "CLM-24-0625": ("PV-1021-A", "paid", "9820.00", "0.00", "6800.00", "3020.00", 4, "5.96"),
    # NY: POL 05-10 + 30 calendar = 06-09 -> 21 days. 3300@39m 32.5% = 2227.50; 1240@60m -> cap 80% = 248;
    # 720@6m 10% = 648 -> 3123.50 - 1000 = 2123.50; 2123.50*.09*21/365 = 10.995 -> 11.00
    "CLM-24-0610": ("PV-1009-A", "paid", "3123.50", "0.00", "1000.00", "2123.50", 21, "11.00"),
    # TX Memorial Day: POL Wed 05-22 + 5 bd = Thu 05-30 -> 31 days. 2100@18m 15% = 1785; 2750@36m 60% = 1100;
    # 600@144m -> cap 80% = 120 -> 3005 - 1000 = 2005; 2005*.18*31/365 = 30.652 -> 30.65
    "CLM-24-0611": ("PV-1011-A", "paid", "3005.00", "0.00", "1000.00", "2005.00", 31, "30.65"),
    # OH: FNOL Sat 05-11 + 10 bd = 05-24 -> 37 days late but interest_applies=false -> 0.00
    "CLM-24-0608": ("PV-1007-A", "paid", "1630.25", "0.00", "500.00", "1130.25", 37, "0.00"),
    # CA: POL 05-25 + 40 = 07-04 -> not late (FNOL-based clock would be 1 day late). jewelry 3100 -> 2500 (-600).
    "CLM-24-0612": ("PV-1012-A", "paid", "5622.50", "600.00", "2500.00", "2522.50", 0, "0.00"),
}


@pytest.mark.parametrize("claim_id", sorted(GOLDEN), ids=sorted(GOLDEN))
def test_unlisted_claim_matches_rules_document(main_run, claim_id):
    version, status, gross, reduction, ded, indemnity, days_late, interest = GOLDEN[claim_id]
    row = main_run.rows[claim_id]
    assert row["policy_version_id"] == version
    assert row["status"] == status
    assert D(row["gross_acv"]) == D(gross)
    assert D(row["sublimit_reduction"]) == D(reduction)
    assert D(row["deductible_applied"]) == D(ded)
    assert D(row["indemnity"]) == D(indemnity)
    assert int(row["days_late"]) == days_late
    assert D(row["interest"]) == D(interest)
