# PR-218 — Port LNACCR01 to Python (pyledger 0.9.0)

**Author:** d.okonkwo · **Reviewers:** m.lindqvist (lending systems, ex-mainframe), r.patel
**Merged:** 2023-11-20 · **Base:** main · 14 files changed · 5 review threads

> Initial port of the monthly accrual batch. Layouts generated from the 2018 copybook
> export on the `ldsys-copybooks` share. Verified against the October 2023 LNOUT sample
> (50 accounts) — all records match.

---

### Review thread

**m.lindqvist** — `pyledger/numeric.py` L12
> `round(value, 2)` — COBOL `ROUNDED` is round-half-away-from-zero, Python's `round`
> is banker's rounding (half to even) and you're rounding a float. Have you checked a
> `.xx5` case? Also, where a COMPUTE is *not* ROUNDED, COBOL truncates to the
> receiving picture; I don't see a truncation anywhere.

**d.okonkwo**
> Checked against the October sample, all 50 accrued amounts match to the cent. Float
> error is way below a cent at these magnitudes. Will revisit if the shadow run shows
> anything.

*Resolved by d.okonkwo — "verified, matches on our sample"*

---

**m.lindqvist** — `pyledger/accrual.py` L31
> The COBOL does this in two steps — `WS-DAILY-RATE` is `PIC 9V9(9)` and is stored
> *before* the multiply. Doing `bal * rate / basis * days` in one expression is not the
> same computation.

**d.okonkwo**
> Mathematically identical; the difference is in the 10th decimal.

*Resolved by d.okonkwo*

---

**m.lindqvist** — `pyledger/copybook.py` L58
> Overpunch decode: you map `}` and `J`–`R` to digits but never flip the sign. Fine as
> long as nothing is negative, but `LM-PRIN-BAL` and `TR-AMOUNT` are both `S9`.

**d.okonkwo**
> Loan balances can't be negative and payments are positive. Left a comment.

*Resolved by d.okonkwo*

---

**r.patel** — `pyledger/dates.py` L22
> `2000 + yy` — the master has originations from the 90s. Does LNACCR01 have a window?

**d.okonkwo**
> Only `LM-ORIG-DATE` could be that old and it isn't used for anything that matters in
> this job. Flagging as follow-up.

*Resolved by d.okonkwo — follow-up LND-3988 (closed, won't fix)*

---

**m.lindqvist** — `pyledger/layouts.py` L20
> Which copybook version is this? I remember a change to LNMAST a few years back that
> reused some of the FILLER.

**d.okonkwo**
> `ldsys-copybooks/2018-export/LNMAST.cpy`, the only export on the share. Total length
> is 120 either way so the offsets line up.

*Resolved by d.okonkwo*

---

**r.patel** — approved
> Looks good to me. Shadow run will catch anything the sample didn't.

**m.lindqvist** — approved with comments
> Approving so we can start the shadow run; please treat the threads above as open
> items rather than closed.
