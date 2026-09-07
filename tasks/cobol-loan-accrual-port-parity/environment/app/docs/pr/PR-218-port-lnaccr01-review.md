# PR-218 — Port LNACCR01 to Python (pyledger 0.9.0)

**Author:** d.okonkwo · **Reviewers:** m.lindqvist (lending systems, ex-mainframe), r.patel
**Merged:** 2023-11-20 · **Base:** main · 14 files changed · 5 review threads

> Initial port of the monthly accrual batch. Layouts generated from the 2018 copybook
> export on the `ldsys-copybooks` share. Verified against the October 2023 LNOUT sample
> (50 accounts) — all records match.

---

### Review thread

**m.lindqvist** — rounding
> Are we certain every money result comes out the way the mainframe stores it — the
> exact half-cent cases, and the intermediate values LNACCR01 stores without ROUNDED?
> The October sample is 50 current accounts; I don't think it exercises either.

**d.okonkwo**
> Checked against the October sample, all 50 accrued amounts match to the cent. Will
> revisit if the shadow run shows anything.

*Resolved by d.okonkwo — "verified, matches on our sample"*

---

**m.lindqvist** — accrual arithmetic
> Have you walked the accrual through the COBOL working-storage items one by one rather
> than as a formula? LNACCR01 does not compute it in a single statement, and with
> ARITH(EXTEND) the order of stores matters.

**d.okonkwo**
> Mathematically identical; any difference would be far below a cent.

*Resolved by d.okonkwo*

---

**m.lindqvist** — signed fields
> What happens to a signed DISPLAY field whose value is negative — on the way in and on
> the way out? `LM-PRIN-BAL` and `TR-AMOUNT` are both `S9`, and the October sample has
> none.

**d.okonkwo**
> Loan balances can't be negative and payments are positive.

*Resolved by d.okonkwo*

---

**r.patel** — two-digit years
> The master has originations from the 90s. Have you checked how LNACCR01 expands a
> two-digit year before it uses it?

**d.okonkwo**
> Only `LM-ORIG-DATE` could be that old and it isn't used for anything that matters in
> this job. Flagging as follow-up.

*Resolved by d.okonkwo — follow-up LND-3988 (closed, won't fix)*

---

**m.lindqvist** — copybook version
> Which copybook version were these layouts generated from? I remember LNMAST changing
> a few years back.

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
