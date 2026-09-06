"""Command-line entry point.

    python -m tessera.cli build-db --data data --out data/claims.db
    python -m tessera.cli adjudicate --db data/claims.db --as-of 2024-06-30 --batch 2024-06 --out out/audit_2024-06.csv

The adjudication run never consults the wall clock: --as-of is the payment date
used for prompt-pay interest and recorded on every payment.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from tessera.adjudication.engine import run_batch
from tessera.reports.audit_export import write_export
from tessera.storage import db

log = logging.getLogger("tessera.cli")


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date {value!r}; expected YYYY-MM-DD") from exc


def _batch(value: str) -> str:
    if len(value) != 7 or value[4] != "-" or not (value[:4] + value[5:]).isdigit():
        raise argparse.ArgumentTypeError(f"invalid batch {value!r}; expected YYYY-MM")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tessera", description="tessera-claims adjudication service")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build-db", help="create a sqlite database from the CSV/JSON data directory")
    b.add_argument("--data", required=True, type=Path, help="directory holding policies.csv, claims.csv, ...")
    b.add_argument("--out", required=True, type=Path, help="sqlite file to (re)create")

    a = sub.add_parser("adjudicate", help="adjudicate a monthly batch and export the auditor CSV")
    a.add_argument("--db", required=True, type=Path)
    a.add_argument("--as-of", required=True, type=_iso_date, help="payment date (YYYY-MM-DD)")
    a.add_argument("--batch", required=True, type=_batch, help="batch month (YYYY-MM): claims received in that month")
    a.add_argument("--out", required=True, type=Path, help="export CSV path")
    return parser


def cmd_build_db(args: argparse.Namespace) -> int:
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        args.out.unlink()
    conn = db.connect(args.out)
    try:
        db.init_schema(conn)
        db.load_data_dir(conn, args.data)
        n_claims = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
        n_pay = conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
    finally:
        conn.close()
    log.info("built %s from %s (%d claims, %d historical payments)", args.out, args.data, n_claims, n_pay)
    return 0


def cmd_adjudicate(args: argparse.Namespace) -> int:
    if not args.db.exists():
        log.error("database %s does not exist; run build-db first", args.db)
        return 2
    conn = db.connect(args.db)
    try:
        log.info("batch %s: adjudicating as of %s", args.batch, args.as_of.isoformat())
        results = run_batch(conn, args.batch, args.as_of)
        out = write_export(conn, results, args.out)
    finally:
        conn.close()
    paid = sum(1 for r in results if r.status == "paid")
    uncovered = sum(1 for r in results if r.status == "no_coverage")
    total = sum((r.payment_total for r in results), start=0)
    log.info("batch %s: %d claims (%d paid, %d no coverage), total payments %s -> %s",
             args.batch, len(results), paid, uncovered, f"{total:.2f}", out)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stderr,
    )
    if args.command == "build-db":
        return cmd_build_db(args)
    if args.command == "adjudicate":
        return cmd_adjudicate(args)
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
