-- recon ledger, schema version 1 (baseline). Later versions live in recon/store/migrations.py.

CREATE TABLE IF NOT EXISTS customers (
    customer_id  INTEGER PRIMARY KEY,
    legal_name   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invoices (
    id            INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
    reference     TEXT NOT NULL,
    amount_cents  INTEGER NOT NULL,
    currency      TEXT NOT NULL DEFAULT 'EUR',
    due_date      TEXT NOT NULL,             -- ISO-8601 date
    status        TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'paid'))
);

CREATE TABLE IF NOT EXISTS bank_lines (
    line_id         TEXT PRIMARY KEY,
    booking_date    TEXT NOT NULL,
    value_date      TEXT NOT NULL,
    remitter        TEXT,
    iban            TEXT,
    purpose         TEXT,
    amount_cents    INTEGER NOT NULL,
    currency        TEXT NOT NULL,
    statement_file  TEXT
);

CREATE TABLE IF NOT EXISTS match_results (
    line_id       TEXT NOT NULL REFERENCES bank_lines(line_id),
    invoice_id    INTEGER NOT NULL REFERENCES invoices(id),
    rule          TEXT NOT NULL,
    amount_cents  INTEGER NOT NULL,
    PRIMARY KEY (line_id, invoice_id)
);
