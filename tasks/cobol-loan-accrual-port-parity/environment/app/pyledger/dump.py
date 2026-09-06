"""Decode a fixed-width dataset with one of the copybook layouts and print it (debug aid)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from .layouts import LAYOUTS, LNOUT_DETAIL, LNOUT_TRAILER, REC_TYPE_OFFSET, REC_TYPE_TRAILER


def dump(path: str | Path, layout_name: str, limit: int | None, stream: TextIO) -> int:
    layout_name = layout_name.upper()
    data = Path(path).read_bytes()
    if layout_name == "LNOUT":
        step = LNOUT_DETAIL.record_length + len(LNOUT_DETAIL.terminator)
        records = [data[i:i + step][: LNOUT_DETAIL.record_length] for i in range(0, len(data), step)]
        layouts = [
            LNOUT_TRAILER if r[REC_TYPE_OFFSET:REC_TYPE_OFFSET + 1] == REC_TYPE_TRAILER.encode() else LNOUT_DETAIL
            for r in records
        ]
    elif layout_name == "RATETBL":
        hdr, tier = LAYOUTS["RATETBL-HDR"], LAYOUTS["RATETBL-TIER"]
        step = tier.record_length + 1
        records = [data[i:i + step][: tier.record_length] for i in range(0, len(data), step)]
        layouts = [hdr] + [tier] * (len(records) - 1)
    elif layout_name in LAYOUTS:
        layout = LAYOUTS[layout_name]
        records = layout.read_records(data)
        layouts = [layout] * len(records)
    else:
        raise SystemExit(f"unknown layout {layout_name!r}; choose from LNMAST, LNTRAN, RATETBL, LNOUT")

    shown = 0
    for n, (raw, layout) in enumerate(zip(records, layouts), start=1):
        if limit is not None and shown >= limit:
            break
        stream.write(f"--- record {n} ({layout.name})\n")
        for f in layout.fields:
            try:
                value = f.decode(raw)
            except (ValueError, UnicodeDecodeError) as exc:
                value = f"<undecodable: {exc}>"
            raw_text = f.slice(raw).decode("ascii", "replace") if f.pic.usage == "DISPLAY" else f.slice(raw).hex()
            stream.write(f"  {f.name:<18} @{f.offset + 1:>3}+{f.length:<3} {raw_text!r:<18} -> {value!r}\n")
        shown += 1
    stream.write(f"{len(records)} records in {path}\n")
    return 0


def main(path: str, layout: str, limit: int | None) -> int:
    return dump(path, layout, limit, sys.stdout)
