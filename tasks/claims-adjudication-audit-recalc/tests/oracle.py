"""Independent reference computation used by the hidden tests.

This module re-derives every figure in docs/adjudication_rules.md directly from
the CSV/JSON data files using exact rational arithmetic (fractions.Fraction) and
integer-cent rounding.  It deliberately shares no code with the application.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path


def cents_half_up(x: Fraction) -> int:
    """Round an exact rational amount (in currency units) to integer cents, half up."""
    scaled = x * 100
    if scaled < 0:
        raise ValueError("negative money is never expected here")
    whole = scaled.numerator // scaled.denominator
    remainder = scaled - whole
    return whole + (1 if remainder >= Fraction(1, 2) else 0)


def money(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def parse_date(s: str) -> date | None:
    return date.fromisoformat(s) if s else None


def whole_months(start: date, end: date) -> int:
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return months


@dataclass
class Dataset:
    policies: dict = field(default_factory=dict)
    versions: dict = field(default_factory=dict)  # policy_id -> list of version rows
    sublimits: dict = field(default_factory=dict)  # version_id -> {category: cents}
    claims: list = field(default_factory=list)
    items: dict = field(default_factory=dict)  # claim_id -> list of item rows
    history: list = field(default_factory=list)
    schedule: dict = field(default_factory=dict)
    rules: dict = field(default_factory=dict)
    holidays: set = field(default_factory=set)


def load(data_dir: Path) -> Dataset:
    ds = Dataset()

    def rows(name):
        with (data_dir / name).open(newline="") as fh:
            return list(csv.DictReader(fh))

    for r in rows("policies.csv"):
        ds.policies[r["policy_id"]] = r
    for r in rows("policy_versions.csv"):
        ds.versions.setdefault(r["policy_id"], []).append(r)
    for r in rows("coverage_sublimits.csv"):
        ds.sublimits.setdefault(r["version_id"], {})[r["category"]] = cents_half_up(Fraction(r["sublimit"]))
    ds.claims = rows("claims.csv")
    for r in rows("line_items.csv"):
        ds.items.setdefault(r["claim_id"], []).append(r)
    ds.history = rows("payments_history.csv")
    for r in rows("depreciation_schedule.csv"):
        ds.schedule[r["category"]] = r
    for r in rows("holidays_2024.csv"):
        ds.holidays.add(date.fromisoformat(r["date"]))
    ds.rules = json.loads((data_dir / "prompt_pay_rules.json").read_text())
    return ds


def version_in_force(ds: Dataset, policy_id: str, loss: date):
    for v in ds.versions.get(policy_id, []):
        start = date.fromisoformat(v["effective_from"])
        end = parse_date(v["effective_to"])
        if start <= loss and (end is None or loss < end):
            return v
    return None


def item_acv_cents(ds: Dataset, item: dict, loss: date) -> int:
    rule = ds.schedule[item["category"]]
    rcv = Fraction(item["rcv"])
    age = whole_months(date.fromisoformat(item["purchase_date"]), loss)
    if age < int(rule["min_age_months"]):
        dep = Fraction(0)
    else:
        dep = min(Fraction(rule["max_pct"]), Fraction(rule["annual_pct"]) * age / 12)
    return cents_half_up(rcv * (100 - dep) / 100)


def add_business_days(start: date, n: int, holidays: set) -> date:
    d = start
    remaining = n
    while remaining > 0:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in holidays:
            remaining -= 1
    return d


def deadline_for(ds: Dataset, claim: dict, state: str) -> date | None:
    rule = ds.rules[state]
    start = parse_date(claim["proof_of_loss_date"] if rule["clock_start"] == "proof_of_loss" else claim["fnol_date"])
    if start is None:
        return None  # CH-7 section 6: the clock has not started
    if rule["day_type"] == "business":
        return add_business_days(start, int(rule["deadline_days"]), ds.holidays)
    return start + timedelta(days=int(rule["deadline_days"]))


def interest_cents(ds: Dataset, state: str, indemnity_cents: int, days_late: int) -> int:
    rule = ds.rules[state]
    if not rule["interest_applies"] or indemnity_cents <= 0 or days_late <= 0:
        return 0
    rate = Fraction(str(rule["annual_rate_pct"])) / 100
    return cents_half_up(Fraction(indemnity_cents, 100) * rate * days_late / 365)


@dataclass
class Expected:
    claim_id: str
    occurrence_id: str
    policy_id: str
    state: str
    status: str
    version_id: str | None
    gross: int
    sublimit_reduction: int
    deductible_applied: int
    indemnity: int
    days_late: int
    interest: int
    category_acv: dict


def _batch_claims(ds: Dataset, batch: str):
    selected = [c for c in ds.claims if c["received_date"][:7] == batch]
    selected.sort(key=lambda c: (c["loss_date"], c["received_date"], c["claim_id"]))
    return selected


def compute_batch(ds: Dataset, batch: str, as_of: date) -> dict[str, Expected]:
    """Recompute the whole batch from scratch, following the rules document literally."""
    # occurrence ledger seeded from history rows that are NOT part of this batch
    occ_paid: dict[str, int] = {}
    occ_ded: dict[str, int] = {}
    occ_cat: dict[str, dict[str, int]] = {}
    for h in ds.history:
        if h["batch"] == batch:
            continue
        occ = h["occurrence_id"]
        occ_paid[occ] = occ_paid.get(occ, 0) + cents_half_up(Fraction(h["indemnity"]))
        occ_ded[occ] = occ_ded.get(occ, 0) + cents_half_up(Fraction(h["deductible_applied"]))
        cats = occ_cat.setdefault(occ, {})
        for cat, amt in json.loads(h["category_acv"]).items():
            cats[cat] = cats.get(cat, 0) + cents_half_up(Fraction(str(amt)))

    out: dict[str, Expected] = {}
    for claim in _batch_claims(ds, batch):
        cid = claim["claim_id"]
        occ = claim["occurrence_id"]
        policy = ds.policies[claim["policy_id"]]
        loss = date.fromisoformat(claim["loss_date"])
        version = version_in_force(ds, claim["policy_id"], loss)
        if version is None:
            out[cid] = Expected(cid, occ, policy["policy_id"], policy["state"], "no_coverage", None, 0, 0, 0, 0, 0, 0, {})
            continue

        per_cat: dict[str, int] = {}
        for item in ds.items.get(cid, []):
            per_cat[item["category"]] = per_cat.get(item["category"], 0) + item_acv_cents(ds, item, loss)
        gross = sum(per_cat.values())

        limits = ds.sublimits.get(version["version_id"], {})
        prior_cat = occ_cat.get(occ, {})
        attributed: dict[str, int] = {}
        for cat, amt in per_cat.items():
            if cat in limits:
                headroom = max(0, limits[cat] - prior_cat.get(cat, 0))
                attributed[cat] = min(amt, headroom)
            else:
                attributed[cat] = amt
        covered = sum(attributed.values())

        if claim["peril"] in ("wind", "hail") and version["wind_hail_deductible_pct"]:
            deductible = cents_half_up(Fraction(version["wind_hail_deductible_pct"]) / 100 * Fraction(policy["dwelling_limit"]))
        else:
            deductible = cents_half_up(Fraction(version["flat_deductible"]))
        remaining_ded = max(0, deductible - occ_ded.get(occ, 0))
        ded_applied = min(remaining_ded, covered)
        limit_headroom = max(0, cents_half_up(Fraction(version["contents_limit"])) - occ_paid.get(occ, 0))
        indemnity = min(covered - ded_applied, limit_headroom)

        deadline = deadline_for(ds, claim, policy["state"])
        days_late = max(0, (as_of - deadline).days) if deadline is not None else 0
        interest = interest_cents(ds, policy["state"], indemnity, days_late)

        status = "paid" if indemnity > 0 else "zero_payment"
        out[cid] = Expected(cid, occ, policy["policy_id"], policy["state"], status, version["version_id"],
                            gross, gross - covered, ded_applied, indemnity, days_late, interest, attributed)

        occ_paid[occ] = occ_paid.get(occ, 0) + indemnity
        occ_ded[occ] = occ_ded.get(occ, 0) + ded_applied
        cats = occ_cat.setdefault(occ, {})
        for cat, amt in attributed.items():
            cats[cat] = cats.get(cat, 0) + amt
    return out
