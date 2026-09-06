# AUD-2024-117 — Internal Audit: June 2024 contents batch recalculation

| | |
|---|---|
| Audit | Claims Payment Accuracy, Q2 2024 |
| Scope | Batch `2024-06` produced by `tessera-claims` 0.7.2 on 2024-06-30 (`logs/batch_2024-06-30.log`, export `out/audit_2024-06.csv`) |
| Method | Seven claims sampled (stratified by state and claim type) and recomputed by hand from the policy versions, line items and payment ledger against Product & Claims Manual CH-7 (`docs/adjudication_rules.md`). Prompt-pay interest reviewed for every claim with `days_late > 0`. |
| Owner | Claims Platform team |
| Priority | P1 — payments outside policy terms, statutory interest misstated |

Recomputed figures for the seven sampled claims are attached as
`AUD-2024-117_expected.csv` (same column meanings as the batch export).

**Summary.** Five of seven sampled claims were paid incorrectly (two
over-payments, two under-payments, one payment on a policy with no coverage in
force), and every interest figure we re-derived differed from the engine's.
The errors are not confined to the sample: the same patterns recur in the batch
log. We ask engineering to correct the engine (not the individual payments) and
to re-run the batch so that all 30 June claims — not just the seven below —
agree with CH-7.

---

## Finding 1 — CLM-24-0601 (P-1001, TX, theft, loss 2024-05-30) — UNDER-PAID

* Observed: adjudicated under **PV-1001-B** (the 2024-06-01 renewal, deductible
  2500). Gross ACV 5032.00, indemnity 2532.00, 24 days late, interest 29.97.
* Recomputed: the loss occurred on 2024-05-30, before the renewal took effect,
  so **PV-1001-A** (deductible 1000) governs (CH-7 §1.1, §1.2). Gross ACV
  4787.00 — the engine also under-depreciated the 14-month-old laptop and the
  18-month-old camera by treating age in whole years (§3.1/§3.3) — indemnity
  **3787.00**. TX clock: proof of loss Mon 2024-06-03 + 5 business days =
  2024-06-10 → 20 days late → interest **37.35**.
* Impact: indemnity short by 1255.00; interest short by 7.38.
* Note: the claim was *received* on 2024-06-03, which is the date the engine
  appears to key on.

## Finding 2 — CLM-24-0603 (P-1002, TX, theft, loss 2024-05-01) — PAID WITHOUT COVERAGE

* Observed: paid 775.00 indemnity + 20.26 interest under PV-1002-A. The batch
  log shows `WARN ... no policy version of P-1002 in force on received_date
  2024-06-04, falling back to latest (PV-1002-A)`.
* Recomputed: PV-1002-A ran 2023-05-01 → 2024-05-01 and was never renewed. The
  `effective_to` day is not covered (§1.1); the loss date 2024-05-01 has **no
  version in force** and the claim must be reported `no_coverage` with no
  payment (§1.3). Falling back to the latest version is not permitted.
* Impact: 795.26 paid with no coverage. Severity: high.

## Finding 3 — CLM-24-0604 (P-1003, CA, hail, loss 2024-06-08) — OVER-PAID

* Observed: flat deductible 2000.00 applied; gross ACV 10470.00; indemnity
  8470.00.
* Recomputed: PV-1003-A carries a 2 % wind/hail deductible; dwelling limit
  600 000 → deductible **12 000.00** for a hail loss (§4.3). Gross ACV is
  12 645.00 once depreciation is capped at the schedule maximum (garage tools,
  96 months: 50 % cap, not 80 %) and counted in months (§3.3) → indemnity
  **645.00**.
* Impact: over-paid 7825.00.

## Finding 4 — CLM-24-0606 (P-1005, FL, theft, loss 2024-06-02) — OVER-PAID

* Observed: three jewelry items (ACV 900 + 800 + 700) paid in full; only the
  cash item was reduced (150.00). Indemnity 3120.00; interest 2.05 for 2 days
  late.
* Recomputed: the jewelry sublimit of 1500 is an aggregate per occurrence
  (§4.2): attributed 1500.00, reduction 900.00; cash 350 → 200, reduction
  150.00; laptop (16 months) 1393.33. Gross ACV 4143.33, sublimit reduction
  **1050.00**, indemnity **2093.33**. FL clock: FNOL Sun 2024-06-02 + 20
  business days (Juneteenth excluded) = 2024-07-01 → **not late**, interest 0.
* Impact: over-paid 1026.67 indemnity and 2.05 interest.

## Finding 5 — CLM-24-0607 (P-1006, FL, supplemental on OCC-24-0217) — UNDER-PAID

* Observed: deductible 1500.00 applied; jewelry and electronics paid in full;
  indemnity 940.00.
* Recomputed: the original claim CLM-24-0217 (paid 2024-03-31, PAY-24-000117)
  already absorbed the occurrence deductible and used jewelry 1200 /
  electronics 4100 of the sublimits (§2, §4.2, §4.3). Attributed: jewelry
  300.00 (headroom), television 900.00 (headroom; ACV 1150.00 at 14 months),
  bookcase 640.00 → gross 2390.00, reduction 550.00, deductible **0.00**,
  indemnity **1840.00**. FNOL 2024-05-15 + 20 business days = 2024-06-13 → 17
  days late → interest **10.28**. This is exactly the worked example in CH-7
  §4.5.
* Impact: indemnity short by 900.00.

## Finding 6 — CLM-24-0613 (P-1013, FL, fire, loss 2024-06-10) — UNDER-PAID

* Observed: gross ACV 5250.00 (laptop 2100.00 undepreciated, dresser 1250.00
  undepreciated, refrigerator valued at **0.00**), indemnity 4250.00.
* Recomputed per §3: laptop 7 months → 11.6667 % → 1855.00; dresser exactly 6
  months → 5 % → 1187.50; nightstand 5 months → no depreciation → 300.00;
  refrigerator 183 months → capped at 65 % → 840.00; clothing 4 months →
  1600.00. Gross **5782.50**, indemnity **4782.50**.
* Impact: under-paid 532.50. The engine depreciates in whole years and has no
  cap; a 15-year-old appliance was written down to nothing.

## Finding 7 — CLM-24-0617 (P-1015, NY, supplemental on OCC-24-0305) — OVER-PAID / LIMIT BREACHED

* Observed: deductible 1000.00 applied again; indemnity 6180.00; 7 days late,
  interest 10.67.
* Recomputed: PV-1015-A Coverage C limit is 63 000; CLM-24-0305 was paid
  60 000.00 in April (PAY-24-000141) and absorbed the deductible. Headroom is
  3000.00 → deductible 0.00, indemnity **3000.00** (§4.3, §4.4). NY clock:
  proof of loss 2024-05-28 + 30 calendar days = 2024-06-27 → 3 days late →
  interest **2.22**.
* Impact: 3180.00 paid above the occurrence limit; interest over by 8.45.

---

## Compliance note — prompt-pay interest (all June claims with days_late > 0)

None of the interest figures in the export could be reproduced from
`data/prompt_pay_rules.json` and CH-7 §6. Representative cases:

| claim | state | engine | recomputed | why |
|---|---|---|---|---|
| CLM-24-0608 | OH | 37 days late, interest 9.17 | interest **0.00** | OH statute imposes no interest (`interest_applies: false`) |
| CLM-24-0610 | NY | 40 days late, 20.02 | 21 days late, **11.00** | NY clock starts at proof of loss (2024-05-10), 30 calendar days → 2024-06-09 |
| CLM-24-0611 | TX | 37 days late, 36.31 | 31 days late, **30.65** | TX clock starts at proof of loss (Wed 2024-05-22); 5 business days excluding the weekend and Memorial Day → 2024-05-30 |
| CLM-24-0612 | CA | 1 day late, 0.82 | not late, **0.00** | proof of loss 2024-05-25 + 40 calendar days = 2024-07-04 |
| CLM-24-0630 | FL | 33 days late, 23.43 | 31 days late, **18.65** | FNOL 2024-05-01 + 20 business days, Memorial Day excluded → 2024-05-30; indemnity also differs |

Pattern: the engine starts every clock at FNOL regardless of the state's
`clock_start`, ignores `interest_applies`, and its business-day count appears to
include the start day and to ignore the holiday table (Memorial Day 05-27 and
Juneteenth 06-19 both fall inside the June windows). Recomputed interest uses
the recomputed indemnity, the statutory rate, actual days late / 365, rounded
half-up (§6.3, §7).

## Requested action

1. Correct the adjudication engine so the whole June batch agrees with CH-7,
   including supplemental claims and claims with no coverage in force.
2. Re-run batch 2024-06 (`--as-of 2024-06-30`) and provide the new export.
3. Confirm the fix does not depend on the sampled claims: audit will re-sample.
