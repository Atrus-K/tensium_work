# recon — bank statement reconciliation

`recon` matches the credit lines of a bank statement export against the open
invoices in the receivables ledger and writes the reconciliation reports the
finance close depends on. The matching rules are specified in
`docs/matching_rules.md` (normative).

The application is stdlib-only (Python 3.11, `sqlite3`, `csv`).

## Layout

```
recon/
  cli.py                 command line (run / migrate / lookup)
  config.py              matching parameters
  models.py              StatementLine, Invoice, Customer, Candidate, MatchResult
  statements/parser.py   bank CSV export parser (semicolon, German numbers/dates)
  customers/master.py    customer master (customers.csv): IBAN and name lookups
  matching/normalize.py  normalisation + reference-token extraction (spec section 1)
  matching/fuzzy.py      edit distance for rule A2
  matching/candidates.py rules A1, A2, B1, B2, B3
  matching/batch.py      rule B3 (batch payments)
  matching/scoring.py    candidate ranking (spec section 5)
  matching/decision.py   single match per line + reason codes (spec section 7)
  pipeline/              orchestration and per-line stages
  store/                 SQLite repository, schema, migrations
  reporting/writer.py    matches.csv / unmatched.csv / summary.json
scripts/load_ledger.py   (re)build data/recon.db from the ERP CSV exports
tests_unit/              unit tests (python -m pytest tests_unit)
data/                    ledger DB, customer master, statements
docs/, logs/, profiles/  spec, incident and review documents, nightly log, profiles
```

## Running

```
python -m recon.cli run --db data/recon.db \
    --statement data/statements/nordwind_2026-08.csv \
    --customers data/customers.csv \
    --out out/2026-08

python -m recon.cli migrate --db data/recon.db
python -m recon.cli lookup  --db data/recon.db --reference "RE-2026-004471"
```

Options: `--log-level {DEBUG,INFO,WARNING,ERROR}` (default INFO; log goes to
stderr, every pipeline stage logs `stage=<name> ... elapsed=<seconds>s`).

Exit codes: `0` success; `1` `lookup` found no invoice; `2` bad input (missing
file, malformed statement).

Every command applies pending schema migrations to the ledger on start
(`run` before matching, `lookup` before querying, `migrate` does only that),
so an older `data/recon.db` is upgraded automatically; running on an
up-to-date ledger applies nothing.

`lookup` accepts a reference in any formatting variant covered by the
normalisation rules (case, separators, leading zeros) and prints one line per
matching invoice: `id<TAB>customer_id<TAB>reference<TAB>amount<TAB>due_date<TAB>status`.
stdout carries only these invoice lines; when nothing is found, stdout stays
empty, the diagnostic goes to stderr and the exit code is `1`.

## Inputs

* **Statement** (`data/statements/*.csv`): UTF-8, `;`-separated, header
  `Umsatz-ID;Buchungstag;Valutadatum;Auftraggeber;IBAN;Verwendungszweck;Betrag;Waehrung`.
  Dates `DD.MM.YYYY`, amounts German style (`1.234,56`, negative for debits).
  `Umsatz-ID` is the bank's unique transaction id and is used as `line_id`.
* **Customer master** (`data/customers.csv`): `customer_id,legal_name,aliases,ibans`
  with `|`-separated lists.
* **Ledger** (`data/recon.db`): SQLite, built from `data/customers.csv` and
  `data/invoices.csv` by `scripts/load_ledger.py`. Tables `customers`,
  `invoices(id, customer_id, reference, amount_cents, currency, due_date,
  status)`, `bank_lines`, `match_results(line_id, invoice_id, rule,
  amount_cents)`, `schema_version`.

## Output contract (read by downstream close jobs — do not change)

`<out>/matches.csv` — one row per matched statement line, sorted by `line_id`:

```
line_id,booking_date,amount,rule,invoice_ids
NW-2026-08-000001,2026-08-03,1289.32,A1,25278
NW-2026-08-000417,2026-08-05,4130.07,B3,7712|7713|7715
```

`booking_date` ISO-8601, `amount` in EUR with a dot and two decimals, `rule`
one of `A1 A2 B1 B2 B3`, `invoice_ids` ascending, `|`-separated.

`<out>/unmatched.csv` — one row per unmatched line, sorted by `line_id`:

```
line_id,booking_date,amount,reason
```

`reason` one of `DEBIT`, `INVOICE_CONSUMED`, `NO_CANDIDATE` (spec section 7).

`<out>/summary.json`:

```json
{
  "statement": "nordwind_2026-08.csv",
  "lines": 12000,
  "matched_lines": 10649,
  "unmatched_lines": 1351,
  "matched_invoices": 11158,
  "matched_amount_cents": 4489140509,
  "by_rule": {"A1": 6632, "A2": 1800, "B1": 1260, "B2": 600, "B3": 357},
  "unmatched_by_reason": {"DEBIT": 120, "INVOICE_CONSUMED": 200, "NO_CANDIDATE": 1031}
}
```

(The numbers above are what Finance's manual review of the August statement
arrived at; they are the figures the run is expected to reproduce.)

## Persistence contract

After `run`:

* every processed statement line is in `bank_lines` (`INSERT OR REPLACE` by `line_id`);
* every matched (line, invoice) pair is a row in `match_results` with the rule
  and the line's `amount_cents`;
* every matched invoice has `status = 'paid'`; unmatched invoices are untouched;
* `match_results` is append-only: `run` never deletes or rewrites rows written
  by earlier runs (the close jobs reconcile against the full history).

Running the same statement again against the reconciled ledger is allowed:
the invoices paid by the first run are no longer available and the reports
reflect that (its matches are appended to `match_results` like any other run's).

## Development

```
python -m pytest tests_unit -q
python scripts/load_ledger.py --customers data/customers.csv --invoices data/invoices.csv --db data/recon.db
```
