# recon-nightly-timeout-2291

**Category:** Performance / algorithm optimisation (production incident
remediation flavour). **Difficulty:** hard. **Language:** Python 3.11,
stdlib-only application.

## Summary

The workspace is `recon`, a payments-reconciliation engine (~1,100 lines,
17 modules) that matches the credit lines of a German bank statement export
to open invoices in an SQLite receivables ledger using a documented rule set
(exact reference, fuzzy reference, IBAN + amount, remitter name + amount +
date window, and oldest-first batch payments), persists the results and
writes reconciliation reports. After a large tenant was onboarded (12,000
statement lines, ~34,000 open invoices, 3,000 customers) the nightly job no
longer finishes inside its 2-hour watchdog, and an emergency hotfix has
silently disabled batch matching for the largest customers. The agent must
work from the incident ticket, nightly log, cProfile dump, hotfix review and
the matching specification to find and fix several independent root causes
across the matcher, the store layer, the schema/migrations, the customer
master loader and the pipeline, while keeping the CLI, report files and
ledger persistence contract unchanged and reproducing exactly the matches
the specification dictates.

## Evidence trail (in `environment/app`)

* `docs/matching_rules.md` — normative matching specification with worked examples
* `docs/INCIDENT-2291.md` — incident ticket, timeline, Finance acceptance criteria
* `docs/pr-418-review.md` — review thread of the hotfix that added the batch cap
* `logs/recon_nightly_2026-08-31.log` — nightly log excerpt with stage timings and warnings
* `profiles/recon_sample200.cprofile.txt` — cProfile listing of the 200-line sample run
* `README.md` — CLI, input formats, report and persistence contracts
* `data/` — customer master, invoice export (loaded into `data/recon.db` at image build), statements
* `tests_unit/` — the team's existing unit tests

## Dependencies and resources

* Base image `python:3.11-slim`; pip: `pytest==8.4.1` (verifier only). The
  application has no third-party dependencies and runs offline.
* Resources: 2 CPUs, 2 GB RAM, 4 GB disk; agent timeout 60 min (the unfixed
  engine needs ~5-6 s per statement line, which the instruction warns about). The image builds `data/recon.db`
  from the CSV exports with the unfixed loader (schema v1), so the hidden tests
  exercise the automatic migration.
* Fully deterministic (fixed-seed fixtures shipped as static files; the engine
  uses the clock only for log timings).

## Verification design

The hidden suite (32 tests) drives only the documented CLI in subprocesses on
scratch copies of a pristine ledger and inspects the report files and the
SQLite tables; no application internals are imported, so any restructuring
passes. The pristine ledger is built by `tests/conftest.py` from
`tests/fixtures/schema_v1.sql` plus `data/customers.csv` / `data/invoices.csv`
(identical to what the image's `scripts/load_ledger.py` produces), so the
verdict does not depend on the state the agent left `data/recon.db` in
(reconciled a few lines while reproducing, rebuilt at the new schema, ...).

* Performance: the full 12,000-line run must finish in 60 s (the reference
  takes about 1.2 s under the 2-CPU limit, i.e. ~50x headroom; the unfixed code
  needs ~19 h and is killed by the harness after 150 s so pre-apply fails fast)
  and execute at most 300,000 SQLite statements (reference: ~34,000; a per-line
  indexed-SQL design lands around 100,000; the unfixed code executes hundreds of
  millions) while opening at most 100 SQLite connections (reference: 1; the
  unfixed code opens one per candidate invoice). Statements and connections are
  counted by `tests/harness/sitecustomize.py`, which
  is injected via `PYTHONPATH` and wraps `sqlite3.connect` / `sqlite3.Connection`
  before any application import (all import styles and subprocesses covered).
* Correctness: every line's outcome (invoice set + rule, or reason code) is
  compared with `tests/fixtures/ground_truth_*.json`, derived by an independent
  brute-force oracle of the specification; a second hidden 1,500-line statement
  with a different seed guards against tuning to the shipped file. The legacy
  engine, run to completion on the 200-line sample (13.6 min on a loaded
  4-core host; the sample has no large-customer batch payments), reproduces
  the oracle on all 200 lines, confirming spec, oracle and legacy behaviour
  agree on rules A1-B2 and the reason codes.
* Contracts: report columns and ordering, DB persistence (append-only
  `match_results`), schema-column preservation, migration idempotence,
  `lookup` variants (stdout empty on a miss), exit codes, byte-identical
  re-runs, re-run on an already reconciled ledger, `stage=<name> ...
  elapsed=<s>s` lines for the parse/match/report stages on stderr (named in
  the instruction), a `CHANGES.md` of >= 200 characters that mentions the
  batch rule (the instruction asks for it explicitly), and the visible
  `tests_unit/` suite.
* Migration path: every scratch ledger is a genuine schema-v1 ledger, so the
  v1 -> v2 upgrade is exercised by every run; a second `migrate` must leave
  `sqlite_master` and the data unchanged. The `lookup` tests bring their copy
  up to date with `migrate` first (the instruction states that `lookup` also
  self-migrates, as the shipped code does, but the tests only grade the
  formatting-variant contract).
* Exit codes: missing input file and malformed statement (duplicated
  `Umsatz-ID`) -> 2, `lookup` miss -> 1, both without a traceback.

## Fixture provenance

`tests/fixtures/generate_fixtures.py` generates the customer master, ledger
and statements with fixed seeds and derives the ground truth from an
independent brute-force implementation of the specification (it shares no
code with the application). `environment/app/profiles/recon_sample200.cprofile.txt`
is a real cProfile listing of the unfixed engine on the first 25 lines of
`sample_200.csv` (139 s under the profiler).
