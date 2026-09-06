-- tessera-claims sqlite schema.  Monetary columns are stored as TEXT decimals
-- (e.g. '1234.56') so no value ever passes through binary floating point.

CREATE TABLE IF NOT EXISTS policies (
    policy_id       TEXT PRIMARY KEY,
    insured         TEXT NOT NULL,
    state           TEXT NOT NULL,
    dwelling_limit  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS policy_versions (
    version_id                TEXT PRIMARY KEY,
    policy_id                 TEXT NOT NULL REFERENCES policies(policy_id),
    effective_from            TEXT NOT NULL,   -- ISO date, inclusive
    effective_to              TEXT,            -- ISO date, exclusive; NULL = open-ended
    contents_limit            TEXT NOT NULL,
    flat_deductible           TEXT NOT NULL,
    wind_hail_deductible_pct  TEXT             -- NULL when the version has no percentage deductible
);

CREATE TABLE IF NOT EXISTS coverage_sublimits (
    version_id  TEXT NOT NULL REFERENCES policy_versions(version_id),
    category    TEXT NOT NULL,
    sublimit    TEXT NOT NULL,
    PRIMARY KEY (version_id, category)
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id            TEXT PRIMARY KEY,
    policy_id           TEXT NOT NULL REFERENCES policies(policy_id),
    occurrence_id       TEXT NOT NULL,
    claim_type          TEXT NOT NULL,   -- original | supplemental
    peril               TEXT NOT NULL,
    loss_date           TEXT NOT NULL,
    fnol_date           TEXT NOT NULL,
    proof_of_loss_date  TEXT,
    received_date       TEXT NOT NULL,
    status              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS line_items (
    item_id        TEXT PRIMARY KEY,
    claim_id       TEXT NOT NULL REFERENCES claims(claim_id),
    category       TEXT NOT NULL,
    description    TEXT NOT NULL,
    rcv            TEXT NOT NULL,
    purchase_date  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id          TEXT PRIMARY KEY,
    claim_id            TEXT NOT NULL REFERENCES claims(claim_id),
    occurrence_id       TEXT NOT NULL,
    batch               TEXT NOT NULL,   -- YYYY-MM
    payment_date        TEXT NOT NULL,
    policy_version_id   TEXT,
    indemnity           TEXT NOT NULL,
    interest            TEXT NOT NULL,
    deductible_applied  TEXT NOT NULL,
    category_acv        TEXT NOT NULL,   -- JSON object {category: "amount"}
    UNIQUE (claim_id, batch)
);

CREATE TABLE IF NOT EXISTS depreciation_schedule (
    category        TEXT PRIMARY KEY,
    annual_pct      TEXT NOT NULL,
    max_pct         TEXT NOT NULL,
    min_age_months  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS prompt_pay_rules (
    state             TEXT PRIMARY KEY,
    clock_start       TEXT NOT NULL,
    deadline_days     INTEGER NOT NULL,
    day_type          TEXT NOT NULL,
    annual_rate_pct   TEXT NOT NULL,
    interest_applies  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS holidays (
    day   TEXT PRIMARY KEY,
    name  TEXT NOT NULL
);
