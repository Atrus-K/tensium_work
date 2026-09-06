-- schema version 2: stored normalised reference and the indexes the matcher and `lookup` rely on.
-- The reference_norm column itself is added by migrations.py (ALTER TABLE is not idempotent in SQLite).

CREATE INDEX IF NOT EXISTS ix_invoices_reference_norm   ON invoices(reference_norm);
CREATE INDEX IF NOT EXISTS ix_invoices_customer_status  ON invoices(customer_id, status);
CREATE INDEX IF NOT EXISTS ix_match_results_line        ON match_results(line_id);
