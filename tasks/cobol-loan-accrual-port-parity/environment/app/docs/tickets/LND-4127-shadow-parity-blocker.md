# LND-4127 — LNACCR01 shadow run: pyledger output does not reconcile to the mainframe (cutover blocked)

**Type:** Defect · **Priority:** P1 · **Component:** pyledger (LNACCR01 port)
**Reporter:** Finance Systems Control (a.reyes) · **Assignee:** Lending Platform
**Opened:** 2024-04-02 · **Target:** before the April month-end run

## Summary

The March 2024 shadow run of `pyledger` (0.9.3) was reconciled field-by-field against the
mainframe's LNOUT dataset for the same batch (`LEND.PROD.LNOUT.D240331`, delivered here as
`data/MAINFRAME_LNOUT_202403.dat`). The reconciliation report
`logs/recon/recon_LNACCR01_202403.txt` shows **247 of 394 detail records differ in at
least one field (386 field differences) and all three money totals in the trailer
differ.** January and February looked similar; we had attributed those to the
transaction feed problem, which is now fixed, so the March run is the first clean
comparison and it is not acceptable.

Cutover to pyledger is blocked until the reconciliation is clean.

## What we see in the report

Field differences by field (from the report):

| Field | records | Typical difference |
|-------|---------|--------------------|
| DAYS_LATE | 165 | pyledger is one day higher on every late account |
| ACCRUED_INT | 99 | mostly one cent, both directions; a few larger |
| LATE_FEE | 63 | fee charged where the mainframe charged none, none where it charged, and a few one-cent differences |
| STATUS | 46 | letter one bucket more severe than the mainframe; `L` where the mainframe has `C` |
| BALANCE | 7 | credit balances: mainframe shows `}`/`J`–`R` zone, pyledger shows `{`/`A`–`I`; two accounts differ in amount as well |
| ACCR_DAYS | 6 | 061 vs 060 on mortgage accounts |
| trailer | 3 | TOT_ACCRUED, TOT_FEES, TOT_BALANCE |

Examples (LEGACY = mainframe, CANDIDATE = pyledger):

```
1015837329  BALANCE       000000005437J     000000005437A
1015837329  ACCRUED_INT   0000000000{       0000000082A
1016144545  ACCRUED_INT   0000010782B       0000010961I
1016144545  ACCR_DAYS     060               061
1005569313  DAYS_LATE     005               006
1005569313  STATUS        C                 L
1013968811  LATE_FEE      000002000         000000000
1030672778  LATE_FEE      000000000         000001500
1014706888  LATE_FEE      000002003         000002002
```

Account 1015837329 is an overpaid personal loan with a **credit** balance of -54.37 on the
master; the mainframe accrues nothing on it and writes the balance with a negative zone.
Account 1013968811 was originated in 1998 and was 27 days late in March; the mainframe
charged the fee, pyledger did not. Account 1030672778 has the branch late-fee waiver set
on the master; the mainframe charged nothing.

## Acceptance criterion

`python -m pyledger recon --legacy data/MAINFRAME_LNOUT_202403.dat --candidate <pyledger output>`
must report `RESULT: MATCH` (zero record, field and trailer differences) for the March
batch, and the same code must reconcile cleanly on the April and subsequent batches
without further changes. The mainframe output is the reference: **where the mainframe's
arithmetic looks odd (a truncated intermediate, a rounding that does not match Python's,
a sign character in a numeric field) the mainframe is right by definition** — that is
what LNACCR01 does and what the downstream GL feed has been built on since 2011. Do not
"correct" the mainframe's numbers, do not edit the datasets, and do not change the
reconciliation tool to be more lenient.

## Notes from the triage call (2024-04-03)

* m.lindqvist: several of the review threads on PR-218 were closed without changes
  ("matches on our sample"); the sample was 50 current accounts from October. Start there.
* Lending systems confirmed the mainframe compiles LNACCR01 with `ARITH(EXTEND)`; the
  program source and copybooks in `legacy/` are current production (LNMAST copybook v3).
* The Python layouts were generated from the 2018 copybook export on the
  `ldsys-copybooks` share (see CHANGELOG).
* Root-cause fixes only. A per-account or per-batch adjustment will not pass the April
  reconciliation and will be rejected in review.
