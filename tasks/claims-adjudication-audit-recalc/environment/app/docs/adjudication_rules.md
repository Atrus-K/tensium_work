# Homeowners Contents (Coverage C) — Claims Handling Rules

Product & Claims Manual, excerpt CH-7 "Contents adjudication". Revision 2024-03.
This excerpt is the normative reference for `tessera-claims`. Where the code and
this document disagree, the document wins.

All dates are calendar dates (ISO `YYYY-MM-DD`, no time zones). All monetary
amounts are in USD and are handled at cents precision as described in section 7.

---

## 1. Policy version in force

A policy is a sequence of *versions* (new-business term, renewals, mid-term
endorsements). Each version has an `effective_from` date and an `effective_to`
date; `effective_to` may be empty, meaning the version is open-ended.

**Rule 1.1** — A version is in force for a claim when

    effective_from <= loss_date  AND  (effective_to is empty OR loss_date < effective_to)

The interval is half-open: the `effective_from` day is covered, the
`effective_to` day is **not** (it belongs to the next version, if any).

**Rule 1.2** — The lookup is keyed on the claim's **loss date**. The date the
claim was reported (`fnol_date`), the proof-of-loss date and the date it was
received for adjudication are irrelevant to coverage.

**Rule 1.3** — If no version is in force on the loss date, the claim has **no
coverage**: it must not be paid, no deductible is applied, and no payment record
is created. It is reported with status `no_coverage`, zero amounts and
`days_late` 0 (no statutory clock runs on a claim that is not covered). Falling
back to another version (latest, nearest, most recent renewal) is never
permitted.

Examples

| versions | loss date | in force |
|---|---|---|
| A: 2023-06-01 → 2024-06-01, B: 2024-06-01 → 2025-06-01 | 2024-05-30 | A |
| A: 2023-06-01 → 2024-06-01, B: 2024-06-01 → 2025-06-01 | 2024-06-01 | B |
| A: 2023-05-01 → 2024-05-01 (never renewed) | 2024-05-01 | none → `no_coverage` |
| A: 2023-05-01 → 2024-05-01 | 2024-04-30 | A (even if reported in June) |
| A: 2023-03-01 → 2024-03-01, B: 2024-04-15 → 2025-04-15 | 2024-03-20 | none (lapse gap) → `no_coverage` |
| B: 2024-06-01 → (open) | 2031-01-01 | B |

## 2. Occurrences, original and supplemental claims

Every claim belongs to an **occurrence** (`occurrence_id`), which identifies one
loss event. The first claim on an occurrence is the *original*; later claims on
the same occurrence (items found missing later, additional damage) are
*supplemental* claims. All coverage terms — deductible, category sublimits and
the Coverage C limit — apply **per occurrence**, not per claim and not per line
item. A supplemental claim is adjudicated against what the occurrence has
already used:

* indemnity already paid on the occurrence (all earlier payments, whatever batch
  they were made in);
* deductible already absorbed on the occurrence;
* ACV already attributed per category on the occurrence (see 4.2).

Earlier activity comes from the payment ledger: every payment record on the
occurrence counts, whatever batch it belongs to, except the records produced by
an earlier run of the batch being (re-)run — those are replaced, not counted
(section 8). When two claims of the same occurrence are adjudicated in the same
batch, the earlier one in processing order (loss date, then received date, then
claim id) counts as prior activity for the later one; claim ids are assigned at
first notice and do not necessarily follow the order in which claims are
received for adjudication.

## 3. Valuation of line items (ACV)

Each line item has a replacement cost value (`rcv`), a category and a purchase
date. Its actual cash value (ACV) is the RCV less depreciation from the
category schedule (`depreciation_schedule.csv`: `annual_pct`, `max_pct`,
`min_age_months`).

**Rule 3.1 (age)** — Age is the number of **whole calendar months** between the
purchase date and the **loss date**, day-of-month aware:

    months = (loss.year - purchase.year) * 12 + (loss.month - purchase.month)
    if loss.day < purchase.day: months -= 1

| purchase | loss | age (months) |
|---|---|---|
| 2023-12-10 | 2024-06-10 | 6 |
| 2023-12-11 | 2024-06-10 | 5 |
| 2023-11-10 | 2024-06-10 | 7 |
| 2024-01-31 | 2024-02-29 | 0 |
| 2009-03-05 | 2024-06-10 | 183 |

**Rule 3.2 (threshold)** — If `months < min_age_months`, depreciation is 0.

**Rule 3.3 (rate and cap)** — Otherwise

    depreciation_pct = min(max_pct, annual_pct × months / 12)

Depreciation accrues monthly, not in whole years, and never exceeds `max_pct`.

**Rule 3.4 (ACV)** —

    ACV = RCV × (100 − depreciation_pct) / 100,  rounded half-up to cents (section 7)

Each line is rounded on its own; the claim's gross ACV is the sum of the rounded
line ACVs. Categories with `annual_pct = 0` (jewelry, cash, art) are never
depreciated.

Worked examples (electronics: 20 %/yr, max 70 %, min 6 months; appliances:
12.5 %/yr, max 65 %, min 6 months; furniture: 10 %/yr, max 60 %, min 6 months):

| item | rcv | purchase | loss | months | depreciation | ACV |
|---|---|---|---|---|---|---|
| laptop | 2100.00 | 2023-11-10 | 2024-06-10 | 7 | 20×7/12 = 11.6667 % | 1855.00 |
| dresser | 1250.00 | 2023-12-10 | 2024-06-10 | 6 | 5 % | 1187.50 |
| nightstand | 300.00 | 2023-12-11 | 2024-06-10 | 5 | 0 (under 6 months) | 300.00 |
| refrigerator | 2400.00 | 2009-03-05 | 2024-06-10 | 183 | min(65, 190.625) = 65 % | 840.00 |
| side table | 100.30 | 2023-12-15 | 2024-06-15 | 6 | 5 % → 95.285 | 95.29 |

## 4. Order of operations for a covered claim

### 4.1 Gross ACV
Sum of the per-line ACVs (3.4), grouped by category.

### 4.2 Category sublimits (per occurrence, aggregate)
A version may carry a sublimit per category (e.g. jewelry 1500, cash 200). The
sublimit caps the **aggregate** ACV attributed to that category across **all
items and all claims of the occurrence**. For the claim being adjudicated:

    headroom(category)   = max(0, sublimit − ACV already attributed to that category on the occurrence)
    attributed(category) = min(category ACV of this claim, headroom(category))

Categories without a sublimit are attributed in full. The claim's
`sublimit_reduction` is gross ACV minus the sum of attributed amounts, and the
attributed per-category amounts are what the ledger records for the claim (so
later supplemental claims see them as "already attributed").

Example: jewelry sublimit 1500; original claim has three jewelry items with ACV
900, 800 and 700 (total 2400) → attributed 1500, reduction 900. A later
supplemental claim on the same occurrence with a 600 jewelry item has headroom
0 → attributed 0.

### 4.3 Deductible (once per occurrence)
The occurrence deductible is:

* for perils `wind` and `hail`, when the version has a
  `wind_hail_deductible_pct`: `pct / 100 × dwelling_limit`, rounded half-up to
  cents (e.g. 2 % of a 600 000 dwelling limit = 12 000.00);
* otherwise the version's `flat_deductible`.

It is applied **once per occurrence**, to the sublimit-adjusted ACV:

    deductible_remaining = max(0, deductible − deductible already absorbed on the occurrence)
    deductible_applied   = min(deductible_remaining, sum of attributed amounts)

`deductible_applied` is the amount actually absorbed by this claim and is what
the ledger records. If the deductible exceeds the attributed ACV the claim pays
nothing (`indemnity = 0`) but still absorbs `deductible_applied` = attributed
ACV, so a later supplemental claim only bears the remainder.

### 4.4 Coverage C limit (per occurrence)

    limit_headroom = max(0, contents_limit − indemnity already paid on the occurrence)
    indemnity      = min(attributed ACV − deductible_applied, limit_headroom)

Indemnity is never negative. Interest (section 6) is not counted against the
limit.

### 4.5 Worked example — supplemental claim
Version: contents limit 205 000, flat deductible 1500, sublimits jewelry 1500,
electronics 5000. The original claim was paid earlier: indemnity 6430.00,
deductible absorbed 1500.00, attributed {jewelry 1200, electronics 4100,
furniture 2630}. The supplemental claim (same occurrence, theft) has:

| item | ACV | sublimit headroom | attributed |
|---|---|---|---|
| signet ring (jewelry) | 600.00 | 1500 − 1200 = 300 | 300.00 |
| television (electronics) | 1150.00 | 5000 − 4100 = 900 | 900.00 |
| bookcase (furniture) | 640.00 | none | 640.00 |

gross 2390.00; attributed 1840.00; sublimit_reduction 550.00;
deductible_remaining = 1500 − 1500 = 0 → deductible_applied 0.00;
limit_headroom 198 570 → indemnity **1840.00**.

## 5. Statuses

| status | meaning | payment record |
|---|---|---|
| `paid` | covered, indemnity > 0 | yes |
| `zero_payment` | covered, indemnity = 0 (deductible or limit exhausted) | yes (records deductible absorbed / attribution) |
| `no_coverage` | no version in force on the loss date (1.3) | **no** |

## 6. Prompt-pay deadline and statutory interest

Prompt-pay parameters are per state (`prompt_pay_rules.json`):

| field | meaning |
|---|---|
| `clock_start` | `proof_of_loss` → the clock starts on `proof_of_loss_date`; `fnol` → on `fnol_date` |
| `deadline_days` | number of days allowed |
| `day_type` | `business` or `calendar` |
| `annual_rate_pct` | simple annual interest rate, in percent |
| `interest_applies` | `false` → the state imposes no statutory interest; interest is always 0 |

**Rule 6.1 (deadline)**

* `calendar`: `deadline = clock_start_date + deadline_days`.
* `business`: `deadline` is the date `deadline_days` business days after the
  clock start date. A business day is a Monday–Friday that is not listed in the
  holidays table. **The clock start date itself is never counted**; counting
  begins with the next day.

Example (TX: proof_of_loss, 5 business days): proof of loss Wed 2024-05-22 →
Thu 23 (1), Fri 24 (2), Sat/Sun skipped, Mon 27 Memorial Day skipped, Tue 28
(3), Wed 29 (4), Thu 30 (5) → deadline **2024-05-30**.

Example (FL: fnol, 20 business days): FNOL Wed 2024-05-01 → deadline
2024-05-30 (Memorial Day skipped).

Example (NY: proof_of_loss, 30 calendar days): proof of loss 2024-05-10 →
deadline 2024-06-09.

If the clock-start date the state's rule requires is absent (for example the
proof of loss has not been received), the clock has not started: there is no
deadline, `days_late` is 0 and no interest accrues.

**Rule 6.2 (days late)** — `days_late = max(0, payment_date − deadline)` in
calendar days. The payment date of a batch is the `--as-of` date passed to the
run; the engine never reads the system clock.

**Rule 6.3 (interest)**

    interest = indemnity × annual_rate_pct / 100 × days_late / 365,  rounded half-up to cents

Interest is 0 when `interest_applies` is false, when `days_late` is 0, or when
indemnity is 0. Interest is computed on the indemnity only (never on gross ACV
or on the deductible) and is paid in addition to the indemnity
(`payment_total = indemnity + interest`).

Example: indemnity 2005.00, TX 18 %, 31 days late → 2005 × 0.18 × 31 / 365 =
30.6526… → **30.65**.

## 7. Money and rounding

All monetary arithmetic is exact decimal arithmetic (no binary floating point).
Whenever a rule says "rounded to cents" the rounding mode is **half-up** (half
away from zero): 95.285 → 95.29, 185.185 → 185.19, 37.3495 → 37.35. Values are
rounded exactly where the rules say so — per line ACV (3.4), the percentage
deductible (4.3), interest (6.3) — and nowhere else; sums of rounded amounts are
not re-rounded. Exports and ledger records carry two decimals.

## 8. Batches and re-runs

A batch `YYYY-MM` consists of every claim whose `received_date` falls in that
month. Claims are processed in the order (loss_date, received_date, claim_id).
Re-running a batch must be idempotent: it replaces the payment records the same
batch produced earlier (one record per claim per batch, never duplicates) and
yields the identical export.
