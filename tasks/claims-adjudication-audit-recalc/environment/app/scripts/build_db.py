#!/usr/bin/env python3
"""Convenience wrapper: rebuild data/claims.db from the CSV/JSON files in data/."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tessera.cli import main  # noqa: E402

if __name__ == "__main__":
    data = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "data")
    out = sys.argv[2] if len(sys.argv) > 2 else str(ROOT / "data" / "claims.db")
    sys.exit(main(["build-db", "--data", data, "--out", out]))
