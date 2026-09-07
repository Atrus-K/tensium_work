"""Report files: matches.csv, unmatched.csv, summary.json (contract in README.md)."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from recon.matching.candidates import RULES
from recon.matching.decision import REASONS
from recon.models import MatchResult

MATCHES_COLUMNS = ("line_id", "booking_date", "amount", "rule", "invoice_ids")
UNMATCHED_COLUMNS = ("line_id", "booking_date", "amount", "reason")


def format_amount(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


@dataclass
class Summary:
    statement: str
    lines: int = 0
    matched_lines: int = 0
    unmatched_lines: int = 0
    matched_invoices: int = 0
    matched_amount_cents: int = 0
    by_rule: dict[str, int] = field(default_factory=lambda: {r: 0 for r in RULES})
    unmatched_by_reason: dict[str, int] = field(default_factory=lambda: {r: 0 for r in REASONS})

    def to_dict(self) -> dict:
        return {
            "statement": self.statement,
            "lines": self.lines,
            "matched_lines": self.matched_lines,
            "unmatched_lines": self.unmatched_lines,
            "matched_invoices": self.matched_invoices,
            "matched_amount_cents": self.matched_amount_cents,
            "by_rule": dict(self.by_rule),
            "unmatched_by_reason": dict(self.unmatched_by_reason),
        }


def summarize(results: Sequence[MatchResult], statement: str) -> Summary:
    s = Summary(statement=statement, lines=len(results))
    for res in results:
        if res.matched:
            s.matched_lines += 1
            s.matched_invoices += len(res.invoices)
            s.matched_amount_cents += res.line.amount_cents
            s.by_rule[res.rule] = s.by_rule.get(res.rule, 0) + 1
        else:
            s.unmatched_lines += 1
            s.unmatched_by_reason[res.reason] = s.unmatched_by_reason.get(res.reason, 0) + 1
    return s


def write_reports(results: Sequence[MatchResult], out_dir: str | Path, statement: str) -> Summary:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ordered = sorted(results, key=lambda r: r.line.line_id)

    with (out / "matches.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(MATCHES_COLUMNS)
        for res in ordered:
            if res.matched:
                w.writerow(
                    [
                        res.line.line_id,
                        res.line.booking_date.isoformat(),
                        format_amount(res.line.amount_cents),
                        res.rule,
                        "|".join(str(i) for i in res.invoice_ids),
                    ]
                )

    with (out / "unmatched.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(UNMATCHED_COLUMNS)
        for res in ordered:
            if not res.matched:
                w.writerow(
                    [res.line.line_id, res.line.booking_date.isoformat(), format_amount(res.line.amount_cents), res.reason]
                )

    summary = summarize(results, statement)
    with (out / "summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary.to_dict(), fh, indent=2, sort_keys=True)
        fh.write("\n")
    return summary
