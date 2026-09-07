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
  application has no third-party dependencies.
* Resources: 2 CPUs, 2 GB RAM, 4 GB disk. The verifier runs the documented
  CLI in subprocesses on scratch copies of the ledger; post-fix it completes
  in well under a minute, pre-fix the long runs are killed by the harness
  after 150 s.
* Fully offline and deterministic (fixed-seed fixtures shipped as static
  files; the engine uses the clock only for log timings).

## Fixture provenance

`tests/fixtures/generate_fixtures.py` generates the customer master, ledger
and statements with fixed seeds and derives the ground truth from an
independent brute-force implementation of the specification (it shares no
code with the application).
