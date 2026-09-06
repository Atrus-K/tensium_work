# Changelog

## 0.7.2 — 2024-05-28
* scheduler: read per-state statute parameters from `prompt_pay_rules.json`
  instead of the hard-coded 30-day rule (PLAT-402).

## 0.7.1 — 2024-04-16
* depreciation: switch from the hard-coded per-category table to
  `data/depreciation_schedule.csv` (adds `max_pct` and `min_age_months`
  columns supplied by product; consumers to follow) (PLAT-388).

## 0.7.0 — 2024-03-22
* add supplemental claim support: claims carry an `occurrence_id`, payments
  record `deductible_applied` and `category_acv`, engine nets prior payments
  (PLAT-371).
* export: add `sublimit_reduction` and `days_late` columns for audit.

## 0.6.3 — 2024-02-09
* lookup: fall back to the latest policy version with a WARN instead of
  crashing the batch when no version matches (PLAT-355, hotfix after the
  January batch aborted on a renewal-in-flight policy).

## 0.6.2 — 2024-01-18
* business_days helper added for the SLA dashboard (PLAT-340).

## 0.6.0 — 2023-11-30
* initial sqlite-backed batch adjudication and auditor export.
