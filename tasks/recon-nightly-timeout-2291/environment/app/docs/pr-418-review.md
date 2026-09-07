# PR-418 — "batch: skip subset search above 12 invoices (hotfix for RECON-2288)"

*Exported from the code review tool on 2026-09-01 for INCIDENT-2291.*

**Author:** j.reuter  **Reviewers:** s.okafor (payments), m.hartmann (Finance Ops, FYI)
**Merged:** 2026-08-14 17:52 (hotfix branch, 1 approval)

## Description (author)

Customer 1472 of tenant Ostsee-Kontor (Hansen Spedition GmbH & Co. KG) has 41 open
invoices in that tenant's ledger. Since
their first batch payment on 08-13 the nightly hangs in
`matching/batch.py:find_batch` — `itertools.combinations` over 41 invoices is
2^41 subsets. This PR adds `BATCH_SUBSET_CAP = 12` in `config.py` and skips
rule B3 with a warning when a customer has more open invoices than that. 2^12
subsets is fine. Unit tests unchanged (the toy customer has 5 invoices).

## Discussion

**s.okafor** — 2026-08-14 15:03
> I understand why we need something *today*, but I do not think this is the
> fix. Section 4 of `docs/matching_rules.md` does not define B3 as "any subset
> of the customer's invoices that sums to the payment". It says: sort the
> customer's available invoices oldest first (due date, then id), and a run is
> a **contiguous slice** of that order, 2–40 invoices, within 60 days, earliest
> start wins. Nothing in there says "subset". I would not bet that what we
> ship today returns the spec's answer for anyone but the five-invoice toy
> customer in the unit test.

**s.okafor** — 2026-08-14 15:05
> With the cap we silently stop matching batch payments for exactly the
> customers that pay in batches — the big ones. Finance will have to match
> those by hand and nothing in the reports tells them why (the line lands in
> `unmatched.csv` with `NO_CANDIDATE`).

**j.reuter** — 2026-08-14 15:41
> Agreed on all points. The hang is blocking the close tonight, so I'd like to
> merge the cap as a stop-gap and bring rule B3 in line with section 4 in a
> follow-up. I opened RECON-2302 for that and linked the spec section. Is
> that OK?

**s.okafor** — 2026-08-14 16:10
> OK as a stop-gap, with two conditions: (1) the warning must name the cap so
> we can grep for it, (2) RECON-2302 gets done before the Nordwind onboarding
> — they have several customers with 20+ open invoices. Also for the
> follow-up: the 60-day window has to be checked exactly as section 4 words
> it; please add a unit test for a run that sits right on the boundary, I
> would not trust the current check without one.

**m.hartmann** — 2026-08-14 16:30
> From the finance side: the "earliest start wins" rule is not decoration.
> Customers pay their oldest invoices first; when two different runs sum to the
> same amount we must take the older one or our dunning goes to the wrong
> invoices. Please make sure the rewrite keeps that.

**s.okafor** — 2026-08-14 17:40 — *Approved*
> Approving the stop-gap. RECON-2302 is now a blocker for Nordwind.

---

*RECON-2302 status on 2026-09-01: Open, unassigned.*
