# recon — Matching rules (normative)

Version 3.2 — owned by Finance Operations (M. Hartmann) and the payments team.
This document is the single source of truth for how a bank statement line is
matched to open invoices. The engine, the ops tooling and the reconciliation
reports must all agree with it. Where code and this document disagree, the
document wins and the code is a bug.

Amounts are handled in integer cents. Dates are calendar dates (no time zone).

---

## 1. Text normalisation

### 1.1 `normalize(text)`

Every comparison of references, remitter names and customer aliases is done on
the *normalised* form of the text. Normalisation is defined as the following
steps, applied **in this order**:

1. Transliterate German special characters, in either case:
   `ä→ae`, `ö→oe`, `ü→ue`, `Ä→AE`, `Ö→OE`, `Ü→UE`, `ß→ss`.
2. Convert to upper case.
3. In every maximal run of decimal digits, remove leading zeros. A run that
   consists only of zeros becomes the single digit `0`.
   Runs are delimited by any non-digit character, so `2026-004471` contains the
   two runs `2026` and `004471`, while `2026004471` is a single run.
4. Remove every character that is not an ASCII letter `A–Z` or a digit `0–9`.

Examples:

| input                      | normalised          |
|----------------------------|---------------------|
| `RE-2026-004471`           | `RE20264471`        |
| `re 2026/004471`           | `RE20264471`        |
| `RE-2026-4471`             | `RE20264471`        |
| `RE-2026004471`            | `RE2026004471`  (one digit run; not equal to the above) |
| `Müller & Söhne GmbH`      | `MUELLERSOEHNEGMBH` |
| `Bau 0000 Nord`            | `BAU0NORD`          |

Step 3 must run before step 4: once separators are gone the digit groups can
no longer be told apart.

### 1.2 Reference tokens in a purpose text

A *reference token* is every substring of the statement line's purpose text
(`Verwendungszweck`) that matches this pattern, case-insensitively:

```
(?<![A-Za-z0-9])[A-Za-z]{1,3}[ \-/.]?[0-9]{4}[ \-/.]?[0-9]{1,8}(?![0-9])
```

i.e. one to three letters, an optional single separator (space, hyphen, slash
or dot), exactly four digits, an optional single separator, and one to eight
digits; the token must not be immediately preceded by a letter or digit and
must not be immediately followed by a digit. Each token is then normalised with
`normalize()`. The line's *token set* is the set of distinct normalised tokens.

Examples: `Zahlung RE-2026-004471 Danke` → `{RE20264471}`;
`RE 2026 004471, RE 2026 004472` → `{RE20264471, RE20264472}`;
`Rechnung August` → `{}` (no token);
`KD-01188 RE-2026-004471` → `{KD1188, RE20264471}`.

---

## 2. Inputs

### 2.1 Statement lines

A statement line has: `line_id` (the bank's `Umsatz-ID`), `booking_date`,
`value_date`, `remitter` (account holder name), `iban` (may be empty),
`purpose`, `amount_cents` (positive = credit received, negative = debit),
`currency`.

### 2.2 Customer identification

The customer master (`customers.csv`) provides, per customer, a legal name, a
list of aliases and a list of IBANs.

* **By IBAN:** the line's IBAN, with whitespace removed and upper-cased, is
  looked up among the customers' IBANs. An IBAN belongs to at most one
  customer.
* **By name:** `normalize(remitter)` is compared with `normalize()` of every
  customer's legal name and aliases. If exactly one customer carries that
  normalised name it is identified; if the normalised name belongs to two or
  more customers, or to none, **no** customer is identified by name.

### 2.3 Invoices

An invoice has `id`, `customer_id`, `reference`, `amount_cents`, `currency`,
`due_date`, `status` (`open` or `paid`). Only invoices with status `open`
that have not been consumed earlier in the same run (Section 6) are
*available*.

---

## 3. Amount comparison

Two amounts *agree* when `|a − b| ≤ tolerance_cents`. The tolerance is 1 cent
(`0.01 EUR`). The *amount difference* of a candidate is `|a − b|`.

---

## 4. Rules

Rules are evaluated for each line strictly in the order A1, A2, B1, B2, B3.
The first rule that yields at least one candidate decides the line; later
rules are not consulted. A line with `amount_cents ≤ 0` is never matched
(Section 7).

### A1 — exact reference

Candidates: every available invoice whose normalised reference is in the
line's token set and whose amount agrees with the line amount.

### A2 — fuzzy reference

Candidates: every available invoice whose amount agrees with the line amount
and whose normalised reference has Levenshtein distance ≤ 2 to at least one
token of the line's token set. The candidate's *distance* is the minimum over
the tokens. Lines with an empty token set have no A2 candidates. The customer
of the invoice plays no role in A2 (a payer may use an IBAN unknown to the
master).

Levenshtein distance is the standard edit distance with unit-cost insertions,
deletions and substitutions.

### B1 — IBAN and amount

Only if a customer is identified **by IBAN**. Candidates: every available
invoice of that customer whose amount agrees with the line amount.

### B2 — remitter name, amount and date window

Only if a customer is identified **by name** (regardless of whether the IBAN is
known). Candidates: every available invoice of that customer whose amount
agrees with the line amount and whose `due_date` is within 14 calendar days of
the line's `booking_date`, i.e. `|due_date − booking_date| ≤ 14 days`.

### B3 — batch payment (several invoices paid with one transfer)

Only if a customer is identified — by IBAN, or, when the IBAN identifies no
customer, by name. Let `I[0..n-1]` be that customer's available invoices
sorted by `(due_date, id)` ascending (oldest first).

A *run* is a contiguous slice `I[i..j]` (inclusive) with

* length `j − i + 1` between 2 and 40 (inclusive),
* `I[j].due_date − I[i].due_date ≤ 60 days`, and
* the sum of the slice's amounts agreeing with the line amount (Section 3).

Only contiguous slices in this ordering are runs. Arbitrary subsets of the
customer's invoices are **not** considered, even if their amounts sum to the
line amount.

If at least one run exists, the line matches the run with the smallest start
index `i`; among runs with the same start, the shortest. All invoices of the
run are matched to the line.

Worked example — customer with available invoices (oldest first):

| pos | id  | due        | amount  |
|-----|-----|------------|---------|
| 0   | 501 | 2026-05-02 | 120.00  |
| 1   | 507 | 2026-05-18 | 80.00   |
| 2   | 512 | 2026-06-01 | 200.00  |
| 3   | 520 | 2026-06-20 | 80.00   |
| 4   | 533 | 2026-08-14 | 120.00  |

* Payment `280.00` → run `[1..2]` (80 + 200). The subset `{501, 507, 520}`
  also sums to 280 but is not contiguous and is ignored.
* Payment `200.00` → run `[0..1]` (120 + 80). The single invoice 512 also
  has amount 200 but a slice of length 1 is not a run (a single-invoice payment
  is the business of B1/B2, which were already evaluated and found nothing —
  otherwise B3 would not have been reached).
* Payment `400.00` → run `[0..2]` (120 + 80 + 200, 30 days). `[2..4]` also
  sums to 400 but spans 74 days (> 60) and is not a run.
* Payment `320.00` → the subset `{501, 512}` (120 + 200) sums to 320 but is not
  contiguous, and no contiguous slice sums to 320. No run — the line is
  unmatched.
* Payment `480.00` → run `[0..3]` (49 days). `[1..4]` also sums to 480 but
  spans 88 days (> 60) and is not a run — and even inside the window `[0..3]`
  would win because it starts earlier.

---

## 5. Choosing among candidates of the winning rule

For A1, A2, B1 and B2 exactly one invoice is chosen: the candidate with the
smallest key

```
(amount difference, distance, due_date, id)
```

where `distance` is the A2 edit distance and `0` for the other rules. Ties are
impossible because `id` is unique. For B3 the choice is defined in Section 4.

---

## 6. Processing order and one-invoice-one-match

Statement lines are processed in ascending order of `(booking_date, line_id)`
— **not** in file order; banks append late-booked corrections at the end of an
export with earlier booking dates. `line_id` is compared as a string.

An invoice matched to a line is *consumed* for the remainder of the run and
is not available to any later line. Consequently the same amount paid twice by
the same customer (rule B1) matches the invoice with the earliest due date
first and the next one second.

---

## 7. Unmatched lines and reason codes

A line that no rule matches is reported with exactly one reason code:

| code               | when                                                                                                                                                                             |
|--------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `DEBIT`            | `amount_cents ≤ 0` (fees, charge-backs, outgoing payments). Checked first; no rule is evaluated.                                                                                  |
| `INVOICE_CONSUMED` | no rule matched and at least one token of the line's token set equals the normalised reference of an invoice that is not available — either status `paid` in the ledger or consumed earlier in this run. |
| `NO_CANDIDATE`     | no rule matched, otherwise.                                                                                                                                                      |

---

## 8. Persisted results

For every matched line one `match_results` row per matched invoice is written
(`line_id`, `invoice_id`, `rule`, `amount_cents` of the line), and every
matched invoice's status becomes `paid`. Every processed statement line is
stored in `bank_lines`. Unmatched lines write nothing to `match_results` and
leave invoices untouched.

---

## 9. Parameters (see `recon/config.py`)

| parameter                 | value |
|---------------------------|-------|
| amount tolerance          | 1 cent |
| A2 maximum edit distance  | 2 |
| B2 date window            | 14 days |
| B3 due-date window        | 60 days |
| B3 maximum run length     | 40 invoices |
| B3 minimum run length     | 2 invoices |

Changes to these values require sign-off by Finance Operations.
