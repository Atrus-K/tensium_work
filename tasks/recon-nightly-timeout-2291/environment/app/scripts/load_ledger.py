"""Build (or rebuild) data/recon.db from the CSV exports of the ERP.

    python scripts/load_ledger.py --customers data/customers.csv --invoices data/invoices.csv --db data/recon.db

invoices.csv columns: id,customer_id,reference,amount_cents,currency,due_date,status
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recon.customers.master import load_customers  # noqa: E402
from recon.models import Invoice  # noqa: E402
from recon.store.repository import Repository  # noqa: E402


def read_invoices(path: Path) -> list[Invoice]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [
            Invoice(
                id=int(r["id"]),
                customer_id=int(r["customer_id"]),
                reference=r["reference"],
                amount_cents=int(r["amount_cents"]),
                currency=r["currency"],
                due_date=date.fromisoformat(r["due_date"]),
                status=r["status"],
            )
            for r in csv.DictReader(fh)
        ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--customers", required=True)
    ap.add_argument("--invoices", required=True)
    ap.add_argument("--db", required=True)
    args = ap.parse_args()

    db = Path(args.db)
    for suffix in ("", "-wal", "-shm", "-journal"):
        p = Path(str(db) + suffix)
        if p.exists():
            p.unlink()
    db.parent.mkdir(parents=True, exist_ok=True)

    customers = load_customers(args.customers)
    invoices = read_invoices(Path(args.invoices))
    repo = Repository(db)
    repo.migrate()
    repo.insert_customers(customers)
    repo.insert_invoices(invoices)
    print(f"{db}: {repo.count('customers')} customers, {repo.count('invoices')} invoices")
    return 0


if __name__ == "__main__":
    sys.exit(main())
