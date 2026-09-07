"""Pipeline orchestration: parse -> match (per line: candidates, decide, persist) -> report.

Every stage logs `stage=<name> ... elapsed=<seconds>s` so the nightly log can
be read for timings.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from recon.config import DEFAULT_CONFIG, MatchConfig
from recon.pipeline.stages import process_line
from recon.reporting.writer import Summary, write_reports
from recon.statements.parser import parse_statement, processing_order
from recon.store.repository import Repository

log = logging.getLogger("recon.pipeline")


class _Stage:
    def __init__(self, name: str):
        self.name = name
        self.t0 = time.perf_counter()

    def done(self, **fields) -> None:
        extra = " ".join(f"{k}={v}" for k, v in fields.items())
        log.info("stage=%s %s elapsed=%.3fs", self.name, extra, time.perf_counter() - self.t0)


def run_pipeline(
    db_path: str | Path,
    statement_path: str | Path,
    customers_path: str | Path,
    out_dir: str | Path,
    config: MatchConfig = DEFAULT_CONFIG,
) -> Summary:
    statement_path = Path(statement_path)

    st = _Stage("parse")
    lines = parse_statement(statement_path)
    st.done(lines=len(lines))

    repo = Repository(db_path)
    repo.migrate()

    st = _Stage("match")
    results = []
    consumed: set[int] = set()
    for n, line in enumerate(processing_order(lines), start=1):
        result = process_line(line, repo, customers_path, consumed, config)
        repo.insert_bank_line(line, statement_path.name)
        repo.mark_matched(result)
        results.append(result)
        if n % 500 == 0:
            log.info("match: %d lines processed", n)
    st.done(matched=sum(1 for r in results if r.matched))

    st = _Stage("report")
    summary = write_reports(results, out_dir, statement_path.name)
    st.done(out=str(out_dir))
    return summary
