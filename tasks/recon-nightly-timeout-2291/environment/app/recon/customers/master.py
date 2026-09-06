"""Customer master (customers.csv) and the IBAN / name lookups of section 2.2.

customers.csv columns: customer_id,legal_name,aliases,ibans
  aliases and ibans are '|' separated lists.
"""
from __future__ import annotations

import csv
from pathlib import Path

from recon.matching.normalize import normalize_iban, normalize_reference
from recon.models import Customer


def load_customers(path: str | Path) -> list[Customer]:
    customers: list[Customer] = []
    with Path(path).open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            aliases = tuple(a.strip() for a in (row.get("aliases") or "").split("|") if a.strip())
            ibans = tuple(normalize_iban(i) for i in (row.get("ibans") or "").split("|") if i.strip())
            customers.append(
                Customer(
                    customer_id=int(row["customer_id"]),
                    legal_name=row["legal_name"].strip(),
                    aliases=aliases,
                    ibans=ibans,
                )
            )
    return customers


class CustomerIndex:
    """Lookups built once per run.

    A normalised name carried by more than one customer identifies nobody
    (section 2.2), so such names are dropped from the name index.
    """

    def __init__(self, customers: list[Customer]):
        self.by_id: dict[int, Customer] = {c.customer_id: c for c in customers}
        self._by_iban: dict[str, Customer] = {}
        by_name: dict[str, set[int]] = {}
        for cust in customers:
            for iban in cust.ibans:
                self._by_iban.setdefault(iban, cust)
            for name in cust.names:
                by_name.setdefault(normalize_reference(name), set()).add(cust.customer_id)
        self._by_name: dict[str, Customer] = {
            norm: self.by_id[next(iter(ids))] for norm, ids in by_name.items() if len(ids) == 1
        }

    def by_iban(self, iban: str) -> Customer | None:
        if not iban:
            return None
        return self._by_iban.get(normalize_iban(iban))

    def by_name(self, remitter: str) -> Customer | None:
        if not remitter:
            return None
        return self._by_name.get(normalize_reference(remitter))

    def __len__(self) -> int:
        return len(self.by_id)


def build_customer_index(path: str | Path) -> CustomerIndex:
    return CustomerIndex(load_customers(path))
