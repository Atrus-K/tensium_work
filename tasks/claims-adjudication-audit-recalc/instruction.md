# AUD-2024-117 — bring the contents adjudication engine back in line with CH-7

You are on the claims-platform team at Tessera Mutual, a small homeowners
insurer. The workspace (`/app`) is `tessera-claims`, the Python 3.11 /
sqlite service that adjudicates the monthly batch of contents (Coverage C)
claims and produces the auditor export. It is pure standard library; there is
no network access.

## What happened

Internal audit recomputed a sample of the June 2024 batch and filed
`docs/tickets/AUD-2024-117_findings.md` (recomputed figures for the seven
sampled claims in `docs/tickets/AUD-2024-117_expected.csv`). Five of the seven
were paid wrongly — over-payments, under-payments and one payment on a policy
with no coverage in force — and none of the prompt-pay interest amounts could
be reproduced. The audit is explicit that the sample is not the extent of the
problem: the same patterns recur across the batch, and they expect the *engine*
to be fixed and the whole batch to agree with the product rules, not the seven
payments to be patched.

Evidence in the workspace:

* `docs/adjudication_rules.md` — Product & Claims Manual CH-7, the normative
  rules the engine must implement (policy version in force, valuation,
  sublimits, deductible, limit, statuses, prompt-pay interest, rounding,
  batches). Where code and document disagree, the document wins.
* `docs/tickets/AUD-2024-117_findings.md` and `AUD-2024-117_expected.csv` — the
  audit ticket and the auditor's figures.
* `logs/batch_2024-06-30.log` — the production log of the run the audit reviewed.
* `data/prompt_pay_rules.json`, `data/holidays_2024.csv`,
  `data/depreciation_schedule.csv` — per-state statute parameters, the holiday
  table and the depreciation schedule the rules refer to.
* `CHANGELOG.md` — how the engine got here.
* `scripts/reconcile_audit.py` — runs the batch into a scratch database and
  diffs the export against the auditor's CSV for the seven sampled claims.
  Useful feedback, but a clean diff on those seven is not the goal.

## What you need to do

Find the root causes and fix the engine so that **every** claim in the June
2024 batch — original claims, supplemental claims sharing an occurrence with
earlier payments, and claims with no coverage in force — is adjudicated exactly
as `docs/adjudication_rules.md` specifies. Expect the causes to be spread across
several modules; the log's WARN lines are one of the clues. Fix causes, not symptoms: hard-coding outcomes for particular
claims, dates or states is not acceptable, and the engine must produce correct
results for any data directory with the same file layout (other policies,
other statute parameters, other batch months and payment dates).

## Contract that must keep working

CLI (unchanged):

```
python -m tessera.cli build-db --data <dir> --out <sqlite file>
python -m tessera.cli adjudicate --db <sqlite file> --as-of YYYY-MM-DD --batch YYYY-MM --out <csv>
```

`build-db` loads any data directory with the same file set as `data/`
(including `payments_history.csv` into the `payments` table). `adjudicate`
processes every claim whose `received_date` falls in the batch month, exits 0,
and never reads the system clock: `--as-of` is the payment date used for
prompt-pay lateness and recorded on the payments.

Export CSV — exactly these columns, in this order, one row per claim in the
batch, money at two decimals:

```
claim_id, occurrence_id, policy_id, state, policy_version_id, status, gross_acv,
sublimit_reduction, deductible_applied, indemnity, days_late, interest, payment_total
```

`status` is one of `paid`, `zero_payment`, `no_coverage` as defined in CH-7 §5.
A claim with no policy version in force on its loss date is reported as
`no_coverage` with an empty `policy_version_id`, `days_late` 0 and all amounts
0, and gets no payment record. `deductible_applied` is the deductible actually absorbed by the
claim; `payment_total = indemnity + interest`.

Ledger — the `payments` table keeps its schema (`tessera/storage/schema.sql`).
Every covered claim (including `zero_payment`) gets exactly one row per batch
with `batch`, `payment_date` (= `--as-of`), `policy_version_id`, `indemnity`,
`interest`, `deductible_applied` and `category_acv` (JSON object of the
per-category ACV attributed to the claim after sublimits, as CH-7 §4.2
requires, so later supplemental claims can be netted against it). Historical
rows loaded from `payments_history.csv` must be left as they are. Re-running the
same batch must be idempotent: identical export, no duplicate or drifting
payment rows.

Constraints: do not modify the CSV/JSON source files under `data/` (rebuilding
`data/claims.db` with `build-db` is expected) or anything under `docs/` or
`logs/`; keep
the application standard-library only; the ledger, not the export, is the
source of truth for prior activity on an occurrence.

When you are done, `python -m tessera.cli adjudicate --db data/claims.db
--as-of 2024-06-30 --batch 2024-06 --out out/audit_2024-06.csv` should
reproduce the auditor's figures for the sampled claims and satisfy CH-7 for the
rest of the batch (rebuild `data/claims.db` with `build-db` first if you have
run the old engine against it).
