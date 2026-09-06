# tessera-claims

Homeowners contents (Coverage C) claims adjudication service for the Tessera
Mutual claims platform. Pure Python 3.11 standard library, sqlite storage.

## Layout

```
tessera/
  cli.py                   command-line entry point (build-db, adjudicate)
  models.py                dataclasses shared by every layer
  storage/schema.sql       sqlite DDL
  storage/db.py            loaders (data/ CSV+JSON -> sqlite) and typed readers
  policy/lookup.py         which policy version applies to a claim
  policy/coverage.py       deductible, limit, category sublimits of a version
  valuation/depreciation.py  RCV -> ACV
  adjudication/rounding.py money helpers
  adjudication/engine.py   per-claim adjudication and batch runner
  payments/ledger.py       payment ledger (prior activity, idempotent writes)
  payments/scheduler.py    prompt-pay deadline and statutory interest
  calendar/business_days.py
  reports/audit_export.py  auditor CSV
scripts/build_db.py        rebuild data/claims.db
scripts/reconcile_audit.py diff a fresh run against the auditor's figures
data/                      reference data (policies, versions, claims, line items, ...)
docs/adjudication_rules.md product rules the engine implements (normative)
docs/tickets/              audit / incident tickets
logs/                      production batch logs
```

## Running

```
python -m tessera.cli build-db --data data --out data/claims.db
python -m tessera.cli adjudicate --db data/claims.db --as-of 2024-06-30 --batch 2024-06 --out out/audit_2024-06.csv
```

`--as-of` is the payment date used for prompt-pay interest and recorded on the
payments; the service never reads the system clock. `--batch YYYY-MM` selects
every claim received in that month.

## Export columns

`claim_id, occurrence_id, policy_id, state, policy_version_id, status,
gross_acv, sublimit_reduction, deductible_applied, indemnity, days_late,
interest, payment_total`
