"""RATETBL loading and tier lookup (1200-LOAD-RATE-TABLE / 3200-FIND-TIER)."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from .layouts import RATETBL_HEADER, RATETBL_TIER
from .models import RateTier


class RateTable:
    def __init__(self, tiers: list[RateTier], description: str = ""):
        if not tiers:
            raise ValueError("rate table has no tiers")
        self.tiers = tiers
        self.description = description.rstrip()

    @classmethod
    def load(cls, path: str | Path) -> "RateTable":
        data = Path(path).read_bytes()
        step = RATETBL_TIER.record_length + 1
        if len(data) % step:
            raise ValueError(f"RATETBL: length {len(data)} is not a multiple of {step}")
        records = [data[i:i + step] for i in range(0, len(data), step)]
        header = RATETBL_HEADER.decode(records[0][:-1])
        if header["RH-REC-TYPE"] != "H":
            raise ValueError("RATETBL: first record is not the header")
        count = int(header["RH-TIER-COUNT"])
        tiers: list[RateTier] = []
        for ix, raw in enumerate(records[1:1 + count], start=1):
            row = RATETBL_TIER.decode(raw[:-1])
            if row["RT-REC-TYPE"] != "T":
                raise ValueError(f"RATETBL: tier {ix} is not a tier record")
            tiers.append(
                RateTier(
                    index=ix,
                    upper_balance=row["RT-UPPER-BAL"],
                    annual_rate=row["RT-ANNUAL-RATE"],
                    late_pct=row["RT-LATE-PCT"],
                    fee_min=row["RT-FEE-MIN"],
                    fee_max=row["RT-FEE-MAX"],
                )
            )
        if len(tiers) != count:
            raise ValueError(f"RATETBL: header announces {count} tiers, found {len(tiers)}")
        return cls(tiers, header["RH-DESCRIPTION"])

    def find_tier(self, balance: Decimal) -> RateTier:
        """First tier whose upper bound is not exceeded by *balance*; the last tier catches the rest.

        PERFORM VARYING WS-TIER-IX FROM 1 BY 1
            UNTIL WS-TIER-IX > RH-TIER-COUNT OR WS-NEW-BAL <= RT-UPPER-BAL(WS-TIER-IX)
        """
        for tier in self.tiers:
            if balance <= tier.upper_balance:
                return tier
        return self.tiers[-1]
