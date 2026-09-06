# cobol-loan-accrual-port-parity

**Category:** Rewriting / cross-language migration (COBOL mainframe batch → Python).
**Difficulty:** hard. **Language:** Python 3.11 (stdlib only).

## Summary

The workspace is `pyledger`, an in-progress Python port of LNACCR01, a z/OS COBOL batch
that reads a fixed-width loan master (zoned and packed decimal fields), a payment
transaction file, a balance-tier rate table and a bank-holiday calendar, applies payments,
accrues interest for the period, assesses tiered late fees, assigns a delinquency status
letter and writes a fixed-width output file with a control-total trailer. The port runs in
shadow mode next to the mainframe and the March 2024 reconciliation shows hundreds of
field-level differences (interest off by a cent, wrong late fees, wrong days-late and
status letters, credit balances losing their sign, wrong trailer totals). Finance has
blocked cutover. The agent must use the reconciliation report, the ticket, the original
PR review, the read-only COBOL source and copybooks to diagnose the port's
semantic-fidelity defects and fix their root causes so that the CLI produces output
byte-identical to the mainframe for the March batch and for any other batch with the same
layouts, verified by the workspace's own `recon` command.

## Evidence trail (in `environment/app`)

* `legacy/LNACCR01.cbl`, `legacy/copybooks/{LNMAST,LNTRAN,RATETBL,LNOUT}.cpy`, `legacy/JCL/LNACCR01.jcl` — authoritative spec (read-only)
* `docs/tickets/LND-4127-shadow-parity-blocker.md` — incident ticket with the cutover acceptance criterion
* `docs/pr/PR-218-port-lnaccr01-review.md` — review thread of the original port
* `docs/file-transfer-notes.md` — dataset encoding conventions on the distributed side
* `logs/recon/recon_LNACCR01_202403.txt` — reconciliation report of the shadow run
* `data/` — March 2024 inputs and the mainframe's output for that batch
* `CHANGELOG.md` — port release history and upstream copybook changes

## Dependencies and resources

* Base image `python:3.11-slim`; pip: `pytest==8.4.1` (verifier only). The application has no
  third-party dependencies.
* Resources: 2 CPUs, 2 GB RAM, 4 GB disk; the verifier runs in well under a minute.
* Fully offline and deterministic: the as-of date is a CLI argument, inputs are static
  fixed-width files, all arithmetic is decimal text in / text out.
