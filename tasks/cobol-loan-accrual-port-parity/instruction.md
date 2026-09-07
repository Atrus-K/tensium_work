# LND-4127 — bring the LNACCR01 port to parity with the mainframe

You are working in `/app`, the `pyledger` repository: a Python 3.11 port of **LNACCR01**,
the monthly loan-accrual / delinquency batch that runs in COBOL on the mainframe. The port
reads the same fixed-width datasets as the mainframe job (loan master `LNMAST`, period
transactions `LNTRAN`, rate-tier table `RATETBL`, bank-holiday calendar) and must write an
`LNOUT` dataset that is **byte-for-byte identical** to the mainframe's for the same inputs and
as-of date. The port has been running in shadow mode; Finance has now blocked cutover because
the March 2024 shadow run does not reconcile. The ticket is in
`docs/tickets/LND-4127-shadow-parity-blocker.md`.

## What is in the workspace

* `pyledger/` — the port. CLI: `python -m pyledger run|recon|dump` (see `README.md`).
* `legacy/LNACCR01.cbl`, `legacy/copybooks/*.cpy`, `legacy/JCL/LNACCR01.jcl` — the production
  COBOL program, its copybooks and JCL. **This is the authoritative specification** of what the
  batch computes and how every field is stored. Treat it as read-only.
* `data/` — the March 2024 batch inputs (`LNMAST_202403.dat`, `LNTRAN_202403.dat`,
  `RATETBL_202403.dat`, `HOLIDAYS.dat`) and the mainframe's own output for that run,
  `data/MAINFRAME_LNOUT_202403.dat`, which is the parity target. Treat `data/` as read-only.
* `logs/recon/recon_LNACCR01_202403.txt` — the reconciliation report from the shadow run
  (one line per differing field: account, field, mainframe value, pyledger value).
* `docs/pr/PR-218-port-lnaccr01-review.md` — the review thread of the original port.
* `docs/file-transfer-notes.md` — how the datasets are encoded on this side (record lengths,
  terminators, zoned-decimal overpunch characters, packed decimal).
* `CHANGELOG.md` — release history, including upstream copybook changes.
* `scripts/run_shadow.sh` — reproduces the shadow run and the reconciliation.

Reproduce the problem with:

```
python -m pyledger run --master data/LNMAST_202403.dat --trans data/LNTRAN_202403.dat \
    --rates data/RATETBL_202403.dat --holidays data/HOLIDAYS.dat \
    --asof 2024-03-31 --out out/LNOUT_202403.dat
python -m pyledger recon --legacy data/MAINFRAME_LNOUT_202403.dat --candidate out/LNOUT_202403.dat
```

`recon` exits 0 and prints `RESULT: MATCH` only when every field of every record and of the
trailer is identical.

## What you need to deliver

Fix the port so that:

1. `python -m pyledger run ...` on the March batch (command above) produces an `LNOUT` file
   identical to `data/MAINFRAME_LNOUT_202403.dat`, and `python -m pyledger recon` reports
   `RESULT: MATCH` with exit status 0.
2. The same code produces mainframe-identical output for **other batches with the same
   layouts** — different accounts, a different number of rate tiers, a different as-of date,
   a different holiday list. The fixes must therefore be root-cause corrections to the port's
   semantics, exactly as `legacy/LNACCR01.cbl` and the copybooks define them — not
   adjustments keyed to particular accounts, values or the March batch.
3. The trailer record stays consistent with the detail records actually written (record
   count, hash total, money totals), as the COBOL defines it.

Things to know, from the ticket and the triage call:

* The mainframe output is authoritative even where its arithmetic looks surprising. LNACCR01
  is compiled with `ARITH(EXTEND)`: intermediate results are exact and precision is lost only
  when a result is stored into a PICTURE-defined item — truncated to the item's scale unless
  `ROUNDED` is coded, in which case it is rounded half away from zero. Reproduce that; do not
  "fix" it.
* Signed DISPLAY fields (`PIC S9...`) carry their sign as an overpunch on the last digit in
  both the input datasets and the output (see `docs/file-transfer-notes.md`).
* The reviewer comments on PR-218 were closed without changes; the shadow run suggests they
  should not have been. Verify the port against the copybooks in `legacy/` as they stand today.
* Expect several independent causes behind the same output field; a mismatch in one field is
  often the consequence of more than one defect.

## Constraints

* Keep the CLI commands, arguments and output file format (80-byte `LNOUT` records plus LF,
  detail records followed by one trailer, as in `legacy/copybooks/LNOUT.cpy`) exactly as they
  are; other tooling depends on them.
* Do not modify anything under `legacy/` or `data/`, and do not change the reconciliation tool
  (`pyledger/recon.py`) — it must keep reporting every byte-level difference.
* No new third-party dependencies; the port must stay standard-library only and work offline.
* Do not hard-code account numbers, batch-specific values or the as-of date anywhere in the
  port.
