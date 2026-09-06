"""pyledger command line.

    python -m pyledger run   --master F --trans F --rates F --holidays F --asof YYYY-MM-DD --out F
    python -m pyledger recon --legacy F --candidate F [--report F]
    python -m pyledger dump  --file F --layout {LNMAST,LNTRAN,RATETBL,LNOUT} [--limit N]

The as-of date is always supplied explicitly (it is the JCL PARM on the mainframe);
the port never consults the wall clock.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .batch import BatchInputs, run_batch
from .dates import parse_asof


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pyledger", description="Python port of mainframe batch LNACCR01")
    parser.add_argument("--version", action="version", version=f"pyledger {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="log progress to stderr")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the accrual batch and write an LNOUT dataset")
    run.add_argument("--master", required=True, help="LNMAST dataset (120-byte records)")
    run.add_argument("--trans", required=True, help="LNTRAN dataset (40-byte records + LF)")
    run.add_argument("--rates", required=True, help="RATETBL dataset (40-byte records + LF)")
    run.add_argument("--holidays", required=True, help="HOLIDAYS.dat bank holiday calendar")
    run.add_argument("--asof", required=True, help="period end / as-of date, YYYY-MM-DD")
    run.add_argument("--out", required=True, help="LNOUT dataset to write (80-byte records + LF)")

    recon = sub.add_parser("recon", help="compare two LNOUT datasets field by field")
    recon.add_argument("--legacy", required=True, help="mainframe LNOUT dataset")
    recon.add_argument("--candidate", required=True, help="pyledger LNOUT dataset")
    recon.add_argument("--report", help="also write the report to this file")

    dump = sub.add_parser("dump", help="decode a dataset with a copybook layout")
    dump.add_argument("--file", required=True)
    dump.add_argument("--layout", required=True, help="LNMAST, LNTRAN, RATETBL or LNOUT")
    dump.add_argument("--limit", type=int, default=None, help="show at most N records")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")

    if args.command == "run":
        inputs = BatchInputs(
            master=Path(args.master),
            transactions=Path(args.trans),
            rates=Path(args.rates),
            holidays=Path(args.holidays),
            asof=parse_asof(args.asof),
            output=Path(args.out),
        )
        totals = run_batch(inputs)
        print(
            f"LNACCR01 as-of {inputs.asof.isoformat()}: {totals.record_count} detail records written to "
            f"{inputs.output} ({totals.skipped_closed} closed accounts skipped)"
        )
        return 0
    if args.command == "recon":
        from .recon import main as recon_main

        return recon_main(args.legacy, args.candidate, args.report)
    if args.command == "dump":
        from .dump import main as dump_main

        return dump_main(args.file, args.layout, args.limit)
    return 2


if __name__ == "__main__":
    sys.exit(main())
