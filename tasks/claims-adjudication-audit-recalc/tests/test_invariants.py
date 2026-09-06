"""Rule-level invariants checked over every claim of both datasets, against an
independent recomputation (tests/oracle.py) of docs/adjudication_rules.md."""
from __future__ import annotations

import json
from decimal import Decimal

import pytest

from conftest import D

MONEY_FIELDS = ("gross_acv", "sublimit_reduction", "deductible_applied", "indemnity", "interest", "payment_total")


def _cents(n: int) -> Decimal:
    return Decimal(n) / 100


def test_every_claim_matches_independent_recomputation(any_run):
    mismatches = []
    for cid, exp in any_run.expected.items():
        row = any_run.rows[cid]
        got = (row["policy_version_id"] or None, row["status"], D(row["gross_acv"]), D(row["sublimit_reduction"]),
               D(row["deductible_applied"]), D(row["indemnity"]), int(row["days_late"]), D(row["interest"]))
        want = (exp.version_id, exp.status, _cents(exp.gross), _cents(exp.sublimit_reduction), _cents(exp.deductible_applied),
                _cents(exp.indemnity), exp.days_late, _cents(exp.interest))
        if got != want:
            mismatches.append(f"{cid}: got {got} want {want}")
    assert not mismatches, "\n".join(mismatches)


def test_money_fields_are_non_negative_two_decimal(any_run):
    for cid, row in any_run.rows.items():
        for f in MONEY_FIELDS:
            v = D(row[f])
            assert v >= 0, f"{cid} {f} negative"
            assert v == v.quantize(Decimal("0.01")), f"{cid} {f}={row[f]} is not at cents precision"
        assert int(row["days_late"]) >= 0


def test_no_coverage_claims_have_zero_amounts_and_no_payment(any_run):
    uncovered = [cid for cid, e in any_run.expected.items() if e.version_id is None]
    assert uncovered, "dataset must contain at least one claim without coverage"
    for cid in uncovered:
        row = any_run.rows[cid]
        assert row["status"] == "no_coverage", cid
        assert row["policy_version_id"] == "", cid
        for f in MONEY_FIELDS:
            assert D(row[f]) == 0, f"{cid} {f}"
        assert any_run.payments_for_claim(cid) == [], f"{cid} must not have a payment row"


def test_covered_claims_have_exactly_one_payment_row_for_the_batch(any_run):
    for cid, e in any_run.expected.items():
        if e.version_id is None:
            continue
        pays = [p for p in any_run.payments_for_claim(cid) if p["batch"] == any_run.batch]
        assert len(pays) == 1, cid


def test_occurrence_indemnity_never_exceeds_contents_limit(any_run):
    ds = any_run.dataset
    for occ in {c["occurrence_id"] for c in ds.claims}:
        pays = any_run.payments_for_occurrence(occ)
        if not pays:
            continue
        total = sum(D(p["indemnity"]) for p in pays)
        version_ids = {p["policy_version_id"] for p in pays if p["policy_version_id"]}
        limits = [D(v["contents_limit"]) for vs in ds.versions.values() for v in vs if v["version_id"] in version_ids]
        assert limits, occ
        assert total <= max(limits), f"{occ}: paid {total} over limit {max(limits)}"


def test_deductible_absorbed_once_per_occurrence(any_run):
    """Across all payments of an occurrence the deductible absorbed equals
    min(occurrence deductible, total attributed ACV) -- never more, never twice."""
    ds = any_run.dataset
    for occ in {c["occurrence_id"] for c in ds.claims}:
        pays = any_run.payments_for_occurrence(occ)
        if not pays:
            continue
        absorbed = sum(D(p["deductible_applied"]) for p in pays)
        attributed = sum(sum(D(v) for v in json.loads(p["category_acv"]).values()) for p in pays)
        # the occurrence deductible from the version actually used
        claim = next(c for c in ds.claims if c["occurrence_id"] == occ)
        version_id = next(p["policy_version_id"] for p in pays if p["policy_version_id"])
        version = next(v for vs in ds.versions.values() for v in vs if v["version_id"] == version_id)
        policy = ds.policies[claim["policy_id"]]
        if claim["peril"] in ("wind", "hail") and version["wind_hail_deductible_pct"]:
            deductible = (D(version["wind_hail_deductible_pct"]) / 100 * D(policy["dwelling_limit"])).quantize(Decimal("0.01"))
        else:
            deductible = D(version["flat_deductible"])
        assert absorbed == min(deductible, attributed), f"{occ}: absorbed {absorbed}, deductible {deductible}, attributed {attributed}"


def test_category_attribution_never_exceeds_sublimit_per_occurrence(any_run):
    ds = any_run.dataset
    checked = 0
    for occ in {c["occurrence_id"] for c in ds.claims}:
        pays = any_run.payments_for_occurrence(occ)
        if not pays:
            continue
        version_id = next(p["policy_version_id"] for p in pays if p["policy_version_id"])
        limits = ds.sublimits.get(version_id, {})
        totals: dict[str, Decimal] = {}
        for p in pays:
            for cat, amt in json.loads(p["category_acv"]).items():
                totals[cat] = totals.get(cat, Decimal(0)) + D(amt)
        for cat, cap in limits.items():
            if cat in totals:
                checked += 1
                assert totals[cat] <= _cents(cap), f"{occ} {cat}: {totals[cat]} > sublimit {_cents(cap)}"
    assert checked > 0


def test_interest_zero_when_not_owed_and_positive_when_late(any_run):
    ds = any_run.dataset
    late_with_interest = 0
    for cid, e in any_run.expected.items():
        row = any_run.rows[cid]
        interest = D(row["interest"])
        applies = e.version_id is not None and ds.rules[e.state]["interest_applies"]
        if not applies or e.indemnity == 0 or e.days_late == 0:
            assert interest == 0, f"{cid}: interest {interest} not owed"
        else:
            assert interest > 0, f"{cid}: late by {e.days_late} days but no interest"
            late_with_interest += 1
    assert late_with_interest >= 3


def test_rerun_is_idempotent(any_run):
    assert any_run.export1.read_bytes() == any_run.export2.read_bytes()
    assert len(any_run.payments_after_first) == len(any_run.payments_after_second)
    strip = lambda p: {k: v for k, v in p.items() if k != "payment_id"}  # noqa: E731
    assert sorted(map(strip, any_run.payments_after_first), key=lambda p: p["claim_id"]) == \
        sorted(map(strip, any_run.payments_after_second), key=lambda p: p["claim_id"])
    ids = [p["claim_id"] + "|" + p["batch"] for p in any_run.payments_after_second]
    assert len(ids) == len(set(ids)), "duplicate (claim_id, batch) payment rows"
