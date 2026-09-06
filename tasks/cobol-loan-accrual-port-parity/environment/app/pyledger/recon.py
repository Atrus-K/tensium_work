"""Shadow-run reconciliation: field-by-field comparison of two LNOUT datasets.

Both files are split into 80-byte records using the LNOUT copybook.  Detail records
are matched on LO-ACCT-NO; every field (FILLER included) is compared as raw bytes,
so any difference in value, sign encoding or padding is reported.  The trailer is
compared field by field as well.  Exit status is 0 only when nothing differs.

This module deliberately does not use the numeric codec: it compares what is on
disk, exactly as Finance's reconciliation job on the mainframe side does.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from .layouts import LNOUT_DETAIL, LNOUT_TRAILER, REC_TYPE_DETAIL, REC_TYPE_OFFSET, REC_TYPE_TRAILER

RECORD_LENGTH = LNOUT_DETAIL.record_length
TERMINATOR = LNOUT_DETAIL.terminator


def _field_label(name: str) -> str:
    # LO-ACCRUED-INT -> ACCRUED_INT ; LT-TOT-FEES -> TOT_FEES
    return name.split("-", 1)[1].replace("-", "_") if "-" in name else name


@dataclass
class ReconResult:
    legacy: str
    candidate: str
    records_compared: int = 0
    records_mismatched: int = 0
    field_mismatches: int = 0
    trailer_mismatches: int = 0
    missing_in_candidate: list[str] = field(default_factory=list)
    extra_in_candidate: list[str] = field(default_factory=list)
    structural_errors: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return (
            self.records_mismatched == 0
            and self.trailer_mismatches == 0
            and not self.missing_in_candidate
            and not self.extra_in_candidate
            and not self.structural_errors
        )


def split_records(data: bytes, label: str, errors: list[str]) -> tuple[dict[str, bytes], list[bytes], list[str]]:
    step = RECORD_LENGTH + len(TERMINATOR)
    if len(data) % step:
        errors.append(f"{label}: file length {len(data)} is not a multiple of {step}")
        data = data[: len(data) - len(data) % step]
    details: dict[str, bytes] = {}
    order: list[str] = []
    trailers: list[bytes] = []
    for i in range(0, len(data), step):
        rec = data[i:i + step]
        if TERMINATOR and not rec.endswith(TERMINATOR):
            errors.append(f"{label}: record {i // step + 1} is not LF-terminated")
        rec = rec[:RECORD_LENGTH]
        rtype = rec[REC_TYPE_OFFSET:REC_TYPE_OFFSET + 1].decode("ascii", "replace")
        if rtype == REC_TYPE_TRAILER:
            trailers.append(rec)
        elif rtype == REC_TYPE_DETAIL:
            key = rec[0:10].decode("ascii", "replace")
            if key in details:
                errors.append(f"{label}: duplicate detail record for account {key}")
            details[key] = rec
            order.append(key)
        else:
            errors.append(f"{label}: record {i // step + 1} has unknown record type {rtype!r}")
    if len(trailers) != 1:
        errors.append(f"{label}: expected exactly one trailer record, found {len(trailers)}")
    return details, trailers, order


def reconcile(legacy_path: str | Path, candidate_path: str | Path) -> ReconResult:
    res = ReconResult(str(legacy_path), str(candidate_path))
    legacy = Path(legacy_path).read_bytes()
    candidate = Path(candidate_path).read_bytes()
    l_details, l_trailers, l_order = split_records(legacy, "legacy", res.structural_errors)
    c_details, c_trailers, _ = split_records(candidate, "candidate", res.structural_errors)

    res.lines.append(f"LNACCR01 RECON  legacy={res.legacy}  candidate={res.candidate}")
    res.lines.append(f"{'ACCT':<10}  {'FIELD':<12}  {'LEGACY':<16}  {'CANDIDATE':<16}")
    for key in l_order:
        if key not in c_details:
            res.missing_in_candidate.append(key)
            res.lines.append(f"{key:<10}  {'<missing>':<12}  {'-':<16}  {'-':<16}")
            continue
        res.records_compared += 1
        lrec, crec = l_details[key], c_details[key]
        mismatched = False
        for f in LNOUT_DETAIL.fields:
            lv, cv = f.slice(lrec), f.slice(crec)
            if lv != cv:
                mismatched = True
                res.field_mismatches += 1
                res.lines.append(
                    f"{key:<10}  {_field_label(f.name):<12}  {lv.decode('ascii', 'replace'):<16}  "
                    f"{cv.decode('ascii', 'replace'):<16}"
                )
        if mismatched:
            res.records_mismatched += 1
    for key in c_details:
        if key not in l_details:
            res.extra_in_candidate.append(key)
            res.lines.append(f"{key:<10}  {'<extra>':<12}  {'-':<16}  {'-':<16}")
    if len(l_trailers) == 1 and len(c_trailers) == 1:
        for f in LNOUT_TRAILER.fields:
            lv, cv = f.slice(l_trailers[0]), f.slice(c_trailers[0])
            if lv != cv:
                res.trailer_mismatches += 1
                res.lines.append(
                    f"{'TRAILER':<10}  {_field_label(f.name):<12}  {lv.decode('ascii', 'replace'):<16}  "
                    f"{cv.decode('ascii', 'replace'):<16}"
                )
    for err in res.structural_errors:
        res.lines.append(f"STRUCTURE   {err}")
    res.lines.append(
        f"SUMMARY records_compared={res.records_compared} records_mismatched={res.records_mismatched} "
        f"field_mismatches={res.field_mismatches} trailer_mismatches={res.trailer_mismatches} "
        f"missing={len(res.missing_in_candidate)} extra={len(res.extra_in_candidate)}"
    )
    res.lines.append("RESULT: MATCH" if res.clean else "RESULT: MISMATCH")
    return res


def write_report(res: ReconResult, stream: TextIO) -> None:
    for line in res.lines:
        stream.write(line.rstrip() + "\n")


def main(legacy: str, candidate: str, report: str | None = None) -> int:
    res = reconcile(legacy, candidate)
    write_report(res, sys.stdout)
    if report:
        Path(report).parent.mkdir(parents=True, exist_ok=True)
        with open(report, "w", encoding="ascii") as fh:
            write_report(res, fh)
    return 0 if res.clean else 1
