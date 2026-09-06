# Changelog — pyledger

## 0.9.3 — 2024-03-04
- `recon`: report `missing` / `extra` accounts separately; non-zero exit on any structural error.
- `dump`: show raw bytes next to the decoded value.

## 0.9.2 — 2024-02-06
- Shadow run for the January and February 2024 batches wired up (`scripts/run_shadow.sh`).
- `run`: closed accounts (`LM-STATUS = 'Z'`) skipped before write and excluded from the trailer,
  matching 3000-PROCESS-MASTER.

## 0.9.1 — 2023-12-12
- Rate table loader follows the RATETBL v2 header (`RH-TIER-COUNT`, OCCURS DEPENDING ON).
- Tier code written to `LO-RATE-TIER` is 1-based like the COBOL OCCURS index.

## 0.9.0 — 2023-11-20 (PR-218)
- Initial port of LNACCR01: master/transaction/rate-table readers, accrual, late fees, status,
  LNOUT writer, business-day roll from `HOLIDAYS.dat`.
- Record layouts authored from the 2018 copybook export in the `ldsys-copybooks` share
  (LNMAST v2, LNTRAN v1, RATETBL v1, LNOUT v2).

## Upstream (mainframe) notes carried over from the LNACCR01 change log
- 2021-04: RATETBL moved to OCCURS DEPENDING ON (max 9 tiers). *(port updated in 0.9.1)*
- 2019-06: **LNMAST copybook bumped to v3** — `LM-WAIVE-FLAG` carved out of the FILLER at column 86,
  honoured by 3500-ASSESS-LATE-FEE.
- 2015-09: new-account late-fee courtesy window added.
