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


def _iban_lookup(customers: list[Customer]) -> dict[str, Customer]:
    table: dict[str, Customer] = {}
    for cust in customers:
        for iban in cust.ibans:
            table.setdefault(iban, cust)
    return table


def _name_lookup(customers: list[Customer]) -> dict[str, Customer]:
    """Normalised legal names and aliases; a name carried by several customers identifies nobody."""
    owners: dict[str, set[int]] = {}
    by_id = {c.customer_id: c for c in customers}
    for cust in customers:
        for name in cust.names:
            owners.setdefault(normalize_reference(name), set()).add(cust.customer_id)
    return {norm: by_id[next(iter(ids))] for norm, ids in owners.items() if len(ids) == 1}


def identify_by_iban(iban: str, customers_path: str | Path) -> Customer | None:
    if not iban:
        return None
    return _iban_lookup(load_customers(customers_path)).get(normalize_iban(iban))


def identify_by_name(remitter: str, customers_path: str | Path) -> Customer | None:
    if not remitter:
        return None
    return _name_lookup(load_customers(customers_path)).get(normalize_reference(remitter))
