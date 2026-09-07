# INCIDENT-2291: nightly reconciliation for tenant Nordwind never finishes

You are on the payments team and own `recon`, the bank-statement
reconciliation engine in this workspace (`/app`). Since tenant Nordwind was
onboarded, the nightly run

```
python -m recon.cli run --db data/recon.db \
    --statement data/statements/nordwind_2026-08.csv \
    --customers data/customers.csv --out <dir>
```

is killed by the 2-hour watchdog every night, and finance has found that the
batch payments of the largest customers are not matched even when the job is
given more time. Read the evidence before touching code:

* `docs/INCIDENT-2291.md` — the incident ticket, timeline and Finance
  Operations' acceptance criteria;
* `logs/recon_nightly_2026-08-31.log` — the nightly log (excerpt) with stage
  timings, store-layer debug output and warnings;
* `profiles/recon_sample200.cprofile.txt` — cProfile of the run on the first
  lines of the 200-line sample `data/statements/sample_200.csv`;
* `docs/pr-418-review.md` — the review thread of the hotfix that introduced
  the 12-invoice cap for rule B3;
* `docs/matching_rules.md` — the normative matching specification;
* `README.md` — CLI, input formats, report and persistence contracts.

Fix the root causes (there are several, in different modules, and more than
one of them is on its own enough to blow the time budget), not the symptoms.
Be careful when reproducing: the unfixed engine needs roughly 5–6 seconds
per statement line, so reproduce with a handful of lines, not with the sample
or the full statement. Reproduce against a *copy* of the ledger: acceptance
starts from the shipped ledger exactly as `scripts/load_ledger.py` builds it
from `data/customers.csv` and `data/invoices.csv` (nothing reconciled yet), so
if you do run anything against `data/recon.db` itself, rebuild it afterwards.

## What must be true when you are done

1. **Performance.** The full statement (12,000 lines against ~34,000 open
   invoices and 3,000 customers) completes with exit code 0 in **under 60
   seconds** on a 2-vCPU machine such as the batch box `fin-batch-02` (this
   workspace's environment, 2 vCPU / 2 GB, is the reference). The same budget
   applies to any other tenant's statement in the same format against the
   same ledger (the older tenants export a fraction of Nordwind's volume,
   ~1,500 lines a month) — do not tune to the shipped file. The run must
   not query the ledger per candidate invoice and must not open a new
   connection per statement line: a full run may execute **at most 300,000
   SQL statements** in total (counted as individual statement executions, so
   an `executemany` over N rows counts N, and `BEGIN`/`COMMIT`/`PRAGMA` count
   too; the current code executes hundreds of millions) and may open **at
   most 100 SQLite connections** (the current code opens one per candidate
   invoice). Any solution must work for other statements in the same format
   against the same ledger, not just the shipped file.

2. **Correctness — `docs/matching_rules.md` is the contract.** Every line's
   result (matched invoice set, rule label, or unmatched reason code) must be
   exactly what the specification dictates, including normalisation, token
   extraction, rule order, the candidate tie-break key, processing order by
   `(booking_date, line_id)`, one-invoice-one-match, the B2 date window and
   the reason codes `DEBIT` / `INVOICE_CONSUMED` / `NO_CANDIDATE`. Rules A1,
   A2, B1 and B2 already behave as specified today — do not change what they
   match. Rule B3 must be implemented as the specification defines it
   (contiguous oldest-first runs, 60-day window, 2–40 invoices, earliest start
   wins) and must work for customers with more than 12 open invoices; the
   PR-418 cap has to go. The 17 large-customer batch payments in the August
   statement must match. The figures in `README.md` (the summary Finance
   arrived at by hand) are what the run has to reproduce.

3. **Contracts unchanged.** The CLI (`run`, `migrate`, `lookup`, their
   arguments and exit codes — `2` for a missing file or a malformed
   statement, `1` for a `lookup` miss, without a traceback), the report files
   `matches.csv`, `unmatched.csv` and `summary.json` (columns, formats, sort
   order) and the persistence contract (`bank_lines`, `match_results`,
   invoice `status`) stay exactly as described in `README.md`. Ops parse the
   stage timings from the nightly log, so `run` must keep logging
   `stage=<name> ... elapsed=<seconds>s` at INFO level to stderr for at least
   the `parse`, `match` and `report` stages (add stages if you like).
   Existing columns of the ledger tables must keep their names and meaning.

4. **Schema changes are allowed, migrations are mandatory.** You may add
   columns, indexes or tables through `recon/store/migrations.py`, but an
   existing `data/recon.db` must be upgraded automatically the next time any
   command starts (`run`, `migrate` and — as today — `lookup` all apply
   pending migrations first), and running again on an already upgraded
   ledger must be a no-op that changes neither schema nor data. Whatever you
   store must be derived by the same normalisation code the matcher uses
   (`normalize_reference`), and `lookup` must find an invoice from any
   formatting variant of its reference as the README promises — check that it
   does on the ledger as shipped.

5. **Determinism and re-runs.** Two runs of the same statement against
   identical copies of the ledger produce byte-identical report files.
   Running a statement again against a ledger it already reconciled must
   succeed and treat the invoices paid by the first run as unavailable.

6. **Housekeeping.** No third-party dependencies (there is no network). The
   unit tests in `tests_unit/` must keep passing (`python -m pytest
   tests_unit`); add your own as you see fit. Write a short `CHANGES.md` (a
   few paragraphs) in the workspace root (`/app/CHANGES.md`) that names each
   root cause you found — the rule B3 cap among them — and what you changed.
