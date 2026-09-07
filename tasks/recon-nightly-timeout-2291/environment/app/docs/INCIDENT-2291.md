# INCIDENT-2291 — Nightly reconciliation for tenant Nordwind killed by watchdog (3 nights running)

| field           | value                                                              |
|-----------------|--------------------------------------------------------------------|
| severity        | S2 (finance close blocked, no data loss)                           |
| opened          | 2026-09-01 02:41 by on-call (T. Bergmann, Platform Ops)            |
| owner           | payments team                                                      |
| affected job    | `recon-nightly` (cron 00:00, batch box `fin-batch-02`, 2 vCPU / 4 GB) |
| affected tenant | Nordwind Handel & Logistik (onboarded 2026-08-24)                  |
| related         | PR-418 (batch subset cap, merged 2026-08-14), RECON-2302 (follow-up, never started) |

## Summary

Since Nordwind was onboarded the nightly reconciliation run no longer finishes.
The job is killed by the 2-hour watchdog every night; no `matches.csv` is
produced, invoices stay open in the ledger and finance has to match the
August statement by hand. Before Nordwind the biggest tenant had ~1,500
statement lines and ~6,000 open invoices per month and the job took 25–40
minutes, which nobody looked at closely.

Nordwind's August statement (`data/statements/nordwind_2026-08.csv`) has
12,000 lines; the ledger (`data/recon.db`) holds ~40,000 invoices of which
~34,000 are open, and the customer master (`data/customers.csv`) has 3,000
customers.

## Timeline (Europe/Berlin)

* **2026-08-14** PR-418 merged: a customer with 41 open invoices had hung the
  job in the batch-payment (rule B3) subset search. The hotfix skips B3 for
  customers with more than 12 open invoices and logs a warning. Review
  thread: `docs/pr-418-review.md`.
* **2026-08-24** Nordwind ledger import (39,537 invoices, 3,000 customers).
* **2026-08-29 02:00** first watchdog kill. On-call restarted manually; killed again at 05:12.
* **2026-08-30 02:00** watchdog kill.
* **2026-08-31 / 09-01 02:00** watchdog kill; log with `DEBUG` enabled for the
  store layer is attached as `logs/recon_nightly_2026-08-31.log` (excerpt —
  the full file was 1.9 GB, almost entirely `sqlite3 connect` lines).
* **2026-09-01 10:30** Ops reproduced with the first 200 lines of the
  statement (`data/statements/sample_200.csv`): **18 min 40 s** for 200 lines.
  cProfile output: `profiles/recon_sample200.cprofile.txt`. Extrapolated,
  the full statement would need roughly 18–19 hours.
* **2026-09-01 11:15** Finance (M. Hartmann) reports that even the manually
  reconciled subset misses the *Sammelüberweisungen* (batch payments) of the
  key accounts; the log shows `batch: candidate set 38 > 12, skipping
  (PR-418 cap)` for exactly those customers.

## What ops observed

1. The `match` stage never completes. Progress lines (`match: 500 lines
   processed`) arrive roughly every 47 minutes.
2. With `--log-level DEBUG` the store layer logs one `sqlite3 connect` line
   per invoice per statement line — tens of thousands of connections per
   line.
3. `top` shows a single core at 100 %; the SQLite file is tiny (4 MB) and
   fully cached; there is no I/O wait. This is CPU-bound Python.
4. The cProfile listing is dominated by `repository.get_invoice`,
   `sqlite3.connect`, `fuzzy.levenshtein`, `master.load_customers` and
   `normalize.normalize_reference`.
5. Warnings `batch: candidate set N > 12, skipping (PR-418 cap)` for 17 lines
   whose remitters are Nordwind's largest customers (13–48 open invoices).

## Acceptance criteria (Finance Operations, M. Hartmann, 2026-09-01)

1. The full Nordwind August statement must reconcile in **under one minute**
   on `fin-batch-02` (2 vCPU). Anything above a few minutes will collide
   with the downstream close jobs again.
2. **No regression** in matching: every line that rules A1, A2, B1 and B2
   matched in the manual review must still match the same invoice with the
   same rule, and every unmatched line must stay unmatched with the reason
   code the spec defines.
3. **Batch payments must match for large customers.** The 17
   Sammelüberweisungen from key accounts (customers with more than 12 open
   invoices) must be matched to the invoices they pay, as rule B3 in
   `docs/matching_rules.md` defines it (contiguous oldest-first runs, 60-day
   window, 2–40 invoices). The PR-418 cap is not an acceptable state.
4. Reports (`matches.csv`, `unmatched.csv`, `summary.json`) and the ledger
   persistence contract (`match_results`, invoice status, `bank_lines`) are
   unchanged — downstream close jobs read them.
5. The result must be **deterministic**: running the same statement twice
   against identical ledgers produces identical reports.
6. The `lookup` tool used by the finance desk must find an invoice from any
   formatting variant of its reference (it currently fails for references
   typed with slashes or without leading zeros), so that finance can
   double-check matches quickly.

## Notes from the payments team stand-up (2026-09-02)

* The matcher was written when tenants had a few hundred invoices; nobody
  re-examined the per-line ledger scan or the per-call `sqlite3.connect`.
* `schema.sql` still carries the `TODO(perf)` about non-sargable reference
  lookups from the first release.
* The customer master used to be 80 rows; reloading it "when needed" was
  free then.
* Whatever we do to the schema must migrate the existing `data/recon.db`
  automatically at startup (ops will not run manual SQL) and must be a no-op
  when run again.
