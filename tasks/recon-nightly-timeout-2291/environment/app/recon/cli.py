"""recon command line.

    python -m recon.cli run     --db data/recon.db --statement <csv> --customers data/customers.csv --out <dir>
    python -m recon.cli migrate --db data/recon.db
    python -m recon.cli lookup  --db data/recon.db --reference "RE-2026-004471"

Exit codes: 0 success, 1 lookup found nothing, 2 bad input.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from recon.pipeline.run import run_pipeline
from recon.reporting.writer import format_amount
from recon.statements.parser import StatementError
from recon.store.repository import Repository


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="recon", description="bank statement reconciliation")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="reconcile a statement against the ledger")
    run.add_argument("--db", required=True)
    run.add_argument("--statement", required=True)
    run.add_argument("--customers", required=True)
    run.add_argument("--out", required=True)

    mig = sub.add_parser("migrate", help="bring the ledger schema up to date")
    mig.add_argument("--db", required=True)

    look = sub.add_parser("lookup", help="find invoices by reference (any formatting variant)")
    look.add_argument("--db", required=True)
    look.add_argument("--reference", required=True)
    return p


def cmd_run(args: argparse.Namespace) -> int:
    for label, path in (("db", args.db), ("statement", args.statement), ("customers", args.customers)):
        if not Path(path).is_file():
            print(f"error: {label} file not found: {path}", file=sys.stderr)
            return 2
    try:
        summary = run_pipeline(args.db, args.statement, args.customers, args.out)
    except StatementError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        f"lines={summary.lines} matched={summary.matched_lines} unmatched={summary.unmatched_lines} "
        f"matched_amount={format_amount(summary.matched_amount_cents)}"
    )
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    with Repository(args.db) as repo:
        applied = repo.migrate()
    print(f"schema up to date ({applied} migration(s) applied)")
    return 0


def cmd_lookup(args: argparse.Namespace) -> int:
    if not Path(args.db).is_file():
        print(f"error: db file not found: {args.db}", file=sys.stderr)
        return 2
    with Repository(args.db) as repo:
        repo.migrate()
        invoices = repo.invoices_by_reference(args.reference)
    if not invoices:
        print("no invoice found", file=sys.stderr)
        return 1
    for inv in invoices:
        print(
            f"{inv.id}\t{inv.customer_id}\t{inv.reference}\t{format_amount(inv.amount_cents)}\t{inv.due_date.isoformat()}\t{inv.status}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    handler = {"run": cmd_run, "migrate": cmd_migrate, "lookup": cmd_lookup}[args.command]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
