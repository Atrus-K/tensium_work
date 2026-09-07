# pyledger — Python port of mainframe batch LNACCR01

`pyledger` re-implements the monthly loan accrual / delinquency batch **LNACCR01**
(COBOL, z/OS) in Python 3.11 with no third-party dependencies. It reads the same
fixed-width datasets the mainframe job reads and must write an `LNOUT` dataset that
is **byte-identical** to the mainframe's for the same inputs and as-of date. The
port has been running in shadow mode next to the mainframe since January 2024;
cutover is gated on a clean reconciliation.

## Layout

```
pyledger/            the port
  __main__.py        CLI: run / recon / dump
  layouts.py         record layouts mirroring legacy/copybooks/*.cpy
  copybook.py        PIC parser + fixed-width codec (DISPLAY, zoned, COMP-3)
  numeric.py         COBOL numeric helpers used by the calculators
  dates.py           YYMMDD date expansion, INTEGER-OF-DATE arithmetic, 30/360, business-day roll
  rates.py           RATETBL loading + tier lookup
  transactions.py    LNTRAN loading + payment application
  accrual.py         interest accrual for the period
  fees.py            days late + late-fee assessment
  status.py          delinquency status letter
  writer.py          LNOUT detail / trailer records
  batch.py           orchestration (the PROCEDURE DIVISION)
  recon.py           field-by-field reconciliation of two LNOUT datasets
  dump.py            decode any dataset with a layout (debug aid)
legacy/              read-only: LNACCR01.cbl, copybooks, JCL — the authoritative spec
data/                March 2024 batch inputs + the mainframe's LNOUT for that run
docs/                tickets, PR review threads, file-transfer conventions
logs/recon/          reconciliation reports from the shadow runs
scripts/run_shadow.sh  reproduce the shadow run + reconciliation
```

## Running

```
python -m pyledger run \
    --master data/LNMAST_202403.dat --trans data/LNTRAN_202403.dat \
    --rates data/RATETBL_202403.dat --holidays data/HOLIDAYS.dat \
    --asof 2024-03-31 --out out/LNOUT_202403.dat

python -m pyledger recon --legacy data/MAINFRAME_LNOUT_202403.dat \
    --candidate out/LNOUT_202403.dat [--report logs/recon/my_run.txt]

python -m pyledger dump --file data/LNMAST_202403.dat --layout LNMAST --limit 3
```

`recon` exits 0 only when every field of every record (and the trailer) matches.
The as-of date is always passed explicitly — it is the JCL PARM on the mainframe —
and nothing in the port reads the wall clock.

See `docs/file-transfer-notes.md` for how the datasets are encoded on this side
(ASCII zoned decimal with overpunch signs, raw COMP-3 bytes, record terminators).
