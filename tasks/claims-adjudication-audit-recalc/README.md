# claims-adjudication-audit-recalc

**Category:** Operations — implementation of real business rules (P&C claims
processing / prompt-pay compliance). **Difficulty:** hard. **Language:** Python 3.11.

## Summary

The workspace is `tessera-claims`, a small insurer's homeowners-contents claims
adjudication service: a ~1,100-line stdlib-only Python package (policy lookup,
coverage terms, depreciation, adjudication engine, payment ledger, prompt-pay
scheduler, business-day calendar, auditor export) over sqlite, driven by a CLI
that adjudicates a monthly batch and writes an auditor CSV. An internal audit
recomputed a sample of the June 2024 batch against the product-rules manual and
found over- and under-payments, a payment on a lapsed policy and misstated
statutory interest. The agent must trace the findings to their root causes,
which span several modules, and fix the engine so the whole batch (not just the
sampled claims) follows the rules document, while preserving the CLI, export
and ledger contract and idempotent re-runs.

## Evidence trail (in `environment/app`)

* `docs/adjudication_rules.md` — normative product rules with worked examples
* `docs/tickets/AUD-2024-117_findings.md`, `docs/tickets/AUD-2024-117_expected.csv` — audit ticket and auditor figures
* `logs/batch_2024-06-30.log` — production log of the audited run
* `data/*.csv`, `data/prompt_pay_rules.json` — reference data (policies, versions, sublimits, claims, line items, payment history, depreciation schedule, holidays, per-state statute parameters)
* `CHANGELOG.md` — release history showing how the behaviour evolved
* `scripts/reconcile_audit.py` — engineering's diff tool for the sampled claims

## Dependencies and resources

* Base image `python:3.11-slim`; pip: `pytest==8.4.1` (verifier only). The application has no third-party dependencies.
* Resources: 2 CPUs, 2 GB RAM, 4 GB disk; the verifier runs in well under a minute.
* Fully offline and deterministic (fixed dates, injected payment date, static data).
