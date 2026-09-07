#!/usr/bin/env python3
"""Fixture generator and independent spec oracle for recon-nightly-timeout-2291.

Deterministic (fixed seeds). Writes

  environment/app/data/customers.csv
  environment/app/data/invoices.csv
  environment/app/data/statements/nordwind_2026-08.csv
  environment/app/data/statements/sample_200.csv      (first 200 rows of the above)
  tests/fixtures/alt_statement_2026-09.csv            (hidden second statement)
  tests/fixtures/ground_truth_full.json
  tests/fixtures/ground_truth_sample200.json
  tests/fixtures/ground_truth_alt.json

Ground truth is produced by `oracle()`, a straightforward re-implementation of
docs/matching_rules.md that shares no code with the engine. The generator also
records what each line was *built* to pay and asserts that the oracle agrees for
every deliberately constructed scenario (tags).
"""
from __future__ import annotations

import csv
import json
import math
import random
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK = HERE.parents[1]
APP = TASK / "environment" / "app"
DATA = APP / "data"

TOL = 1
FUZZY_K = 2
B2_WINDOW = 14
B3_WINDOW = 60
B3_MAX = 40
B3_MIN = 2

# --------------------------------------------------------------------------- #
# Independent implementation of section 1 (normalisation) and Levenshtein
# --------------------------------------------------------------------------- #
_UML = [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("Ä", "AE"), ("Ö", "OE"), ("Ü", "UE"), ("ß", "ss")]
TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{1,3}[ \-/.]?[0-9]{4}[ \-/.]?[0-9]{1,8}(?![0-9])")


def norm(text: str) -> str:
    for a, b in _UML:
        text = text.replace(a, b)
    text = text.upper()
    out = []
    i = 0
    while i < len(text):
        if text[i].isdigit() and text[i] in "0123456789":
            j = i
            while j < len(text) and text[j] in "0123456789":
                j += 1
            run = text[i:j].lstrip("0") or "0"
            out.append(run)
            i = j
        else:
            ch = text[i]
            if "A" <= ch <= "Z" or "0" <= ch <= "9":
                out.append(ch)
            i += 1
    return "".join(out)


def tokens_of(purpose: str) -> list[str]:
    seen: list[str] = []
    for m in TOKEN_RE.finditer(purpose):
        n = norm(m.group(0))
        if n not in seen:
            seen.append(n)
    return seen


def lev(a: str, b: str) -> int:
    m, n = len(a), len(b)
    d = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        d[i][0] = i
    for j in range(n + 1):
        d[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
    return d[m][n]


def norm_iban(s: str) -> str:
    return "".join(s.split()).upper()


# --------------------------------------------------------------------------- #
# Data model for generation
# --------------------------------------------------------------------------- #
@dataclass
class Cust:
    cid: int
    legal: str
    aliases: list[str]
    ibans: list[str]
    kind: str  # small | medium | large | dense


@dataclass
class Inv:
    id: int
    cid: int
    reference: str
    amount: int
    due: date
    status: str


@dataclass
class Line:
    booking: date
    value: date
    remitter: str
    iban: str
    purpose: str
    amount: int
    intent: dict = field(default_factory=dict)  # {"rule":..,"ids":[..]} or {"reason":..}
    tag: str = ""
    late: bool = False
    line_id: str = ""


SURNAMES = [
    "Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Schulz", "Hoffmann",
    "Schäfer", "Koch", "Bauer", "Richter", "Klein", "Wolf", "Schröder", "Neumann", "Schwarz", "Zimmermann",
    "Braun", "Krüger", "Hofmann", "Hartmann", "Lange", "Schmitt", "Werner", "Schmitz", "Krause", "Meier",
    "Lehmann", "Schmid", "Schulze", "Maier", "Köhler", "Herrmann", "König", "Walter", "Mayer", "Huber",
    "Kaiser", "Fuchs", "Peters", "Lang", "Scholz", "Möller", "Weiß", "Jung", "Hahn", "Schubert",
    "Vogel", "Friedrich", "Keller", "Günther", "Frank", "Berger", "Winkler", "Roth", "Beck", "Lorenz",
    "Baumann", "Franke", "Albrecht", "Schuster", "Simon", "Ludwig", "Böhm", "Winter", "Kraus", "Martin",
    "Schumacher", "Krämer", "Vogt", "Stein", "Jäger", "Otto", "Sommer", "Groß", "Seidel", "Heinrich",
    "Brandt", "Haas", "Schreiber", "Graf", "Schulte", "Dietrich", "Ziegler", "Kuhn", "Kühn", "Pohl",
    "Engel", "Horn", "Busch", "Bergmann", "Thomas", "Voigt", "Sauer", "Arnold", "Wolff", "Pfeiffer",
    "Brüggemann", "Lüdtke", "Petersen", "Hansen", "Jansen", "Claußen", "Möhring", "Thießen", "Carstens", "Rehder",
]
INDUSTRIES = [
    "Logistik", "Bau", "Technik", "Handel", "Elektro", "Sanitär", "Metallbau", "Druck", "Verlag", "Spedition",
    "Maschinenbau", "Immobilien", "Gartenbau", "Fahrzeugtechnik", "Systemhaus", "Gebäudereinigung", "Catering",
    "Textil", "Möbel", "Dachdeckerei", "Tiefbau", "Holzbau", "Werbetechnik", "Kältetechnik", "Medizintechnik",
    "Großhandel", "Bäckerei", "Fleischerei", "Schifffahrt", "Hafenservice", "Windkraft", "Solartechnik",
]
FORMS = ["GmbH", "AG", "KG", "GmbH & Co. KG", "e.K.", "OHG", "UG (haftungsbeschränkt)", "GbR"]
CITIES = ["Hamburg", "Kiel", "Lübeck", "Bremen", "Rostock", "Flensburg", "Oldenburg", "Husum", "Stade", "Lüneburg",
          "Cuxhaven", "Emden", "Wilhelmshaven", "Schwerin", "Neumünster"]
FIRST_NAMES = ["Hans", "Petra", "Jens", "Sabine", "Uwe", "Karin", "Thorsten", "Anke", "Björn", "Heike", "Ole",
               "Frauke", "Malte", "Inga", "Sören", "Birte", "Lars", "Maren", "Torben", "Wiebke"]

FLAT = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "Ä": "A", "Ö": "O", "Ü": "U", "ß": "ss"})


def biz_days(year: int, month: int) -> list[date]:
    d = date(year, month, 1)
    out = []
    while d.month == month:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def fmt_amount_de(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    whole, frac = divmod(cents, 100)
    s = f"{whole:,}".replace(",", ".")
    return f"{sign}{s},{frac:02d}"


# --------------------------------------------------------------------------- #
# Customers
# --------------------------------------------------------------------------- #
def make_customers(rng: random.Random, n: int) -> list[Cust]:
    used_norm: set[str] = set()
    used_iban: set[str] = set()
    custs: list[Cust] = []
    kinds = ["small"] * 2450 + ["medium"] * 400 + ["large"] * 130 + ["dense"] * 20
    rng.shuffle(kinds)
    while len(custs) < n:
        pat = rng.random()
        s1 = rng.choice(SURNAMES)
        if pat < 0.45:
            base = f"{s1} {rng.choice(INDUSTRIES)}"
        elif pat < 0.65:
            base = f"{s1} & {rng.choice(SURNAMES)}"
        elif pat < 0.85:
            base = f"{rng.choice(INDUSTRIES)} {rng.choice(CITIES)}"
        else:
            base = f"{s1}"
        form = rng.choice(FORMS)
        legal = f"{base} {form}"
        nl = norm(legal)
        if nl in used_norm or not nl:
            continue
        candidates = [base, legal.translate(FLAT), f"Fa. {base}", base.translate(FLAT)]
        if form == "GmbH & Co. KG":
            candidates.append(f"{base} GmbH u. Co. KG")
        if form == "GmbH":
            candidates.append(f"{base} Ges.m.b.H.")
        if form == "AG":
            candidates.append(f"{base} Aktiengesellschaft")
        aliases: list[str] = []
        rng.shuffle(candidates)
        for a in candidates[: rng.randint(1, 3)]:
            na = norm(a)
            if na and na != nl and na not in used_norm and na not in {norm(x) for x in aliases}:
                aliases.append(a)
        used_norm.add(nl)
        used_norm.update(norm(a) for a in aliases)
        ibans = []
        for _ in range(rng.choice([1, 1, 2, 2, 3])):
            while True:
                body = f"DE{rng.randint(10, 99)}{rng.randint(10000000, 99999999)}{rng.randint(0, 9999999999):010d}"
                if body not in used_iban:
                    used_iban.add(body)
                    break
            if rng.random() < 0.5:
                body = " ".join(body[i : i + 4] for i in range(0, len(body), 4))
            ibans.append(body)
        cid = 1001 + len(custs)
        custs.append(Cust(cid, legal, aliases, ibans, kinds[len(custs)]))
    # two customers deliberately share an alias -> identifies nobody (section 2.2)
    shared = "Nordwind Handel Nord"
    assert norm(shared) not in used_norm
    custs[10].aliases.append(shared)
    custs[11].aliases.append(shared)
    return custs


# --------------------------------------------------------------------------- #
# Invoices
# --------------------------------------------------------------------------- #
def ref_variant(rng: random.Random, seq: int) -> str:
    r = rng.random()
    if r < 0.85:
        return f"RE-2026-{seq:06d}"
    if r < 0.92:
        return f"RE-2026/{seq:06d}"
    if r < 0.96:
        return f"RE 2026 {seq:06d}"
    return f"RE-2026-{seq}"


def rand_amount(rng: random.Random) -> int:
    # log-uniform between 50.00 and 25,000.00 EUR
    eur = math.exp(rng.uniform(math.log(50), math.log(25000)))
    return int(round(eur * 100))


def make_invoices(rng: random.Random, custs: list[Cust]) -> tuple[list[Inv], dict[int, list[int]]]:
    invoices: list[Inv] = []
    start, end = date(2026, 3, 2), date(2026, 9, 18)
    span = (end - start).days
    dup_pairs: dict[int, list[int]] = {}
    next_id = 1
    for c in custs:
        if c.kind == "small":
            count = rng.randint(4, 16)
        elif c.kind == "medium":
            count = rng.randint(17, 28)
        elif c.kind == "large":
            count = rng.randint(29, 48)
        else:  # dense: several invoices per week in Jun-Aug
            count = rng.randint(50, 70)
        amounts: set[int] = set()
        rows = []
        for _ in range(count):
            while True:
                a = rand_amount(rng)
                if all(abs(a - b) > 2 for b in amounts):
                    amounts.add(a)
                    break
            if c.kind == "dense":
                due = date(2026, 6, 1) + timedelta(days=rng.randint(0, 91))
            else:
                due = start + timedelta(days=rng.randint(0, span))
            status = "paid" if rng.random() < 0.15 else "open"
            rows.append((due, a, status))
        rows.sort()
        ids = []
        for due, a, status in rows:
            invoices.append(Inv(next_id, c.cid, ref_variant(rng, next_id), a, due, status))
            ids.append(next_id)
            next_id += 1
        # duplicate-amount pair (both open) for order-conflict scenarios
        opens = [i for i in ids if invoices[i - 1].status == "open"]
        if c.kind in ("small", "medium") and len(opens) >= 4 and rng.random() < 0.04:
            a_id, b_id = rng.sample(opens, 2)
            invoices[b_id - 1].amount = invoices[a_id - 1].amount
            dup_pairs[c.cid] = sorted([a_id, b_id], key=lambda i: (invoices[i - 1].due, i))
    return invoices, dup_pairs


# --------------------------------------------------------------------------- #
# Statement lines
# --------------------------------------------------------------------------- #
class Pool:
    """Tracks which open invoices are still unassigned to any statement line."""

    def __init__(self, invoices: list[Inv], custs: list[Cust]):
        self.inv = {i.id: i for i in invoices}
        self.cust = {c.cid: c for c in custs}
        self.open_by_cust: dict[int, list[Inv]] = defaultdict(list)
        for i in invoices:
            if i.status == "open":
                self.open_by_cust[i.cid].append(i)
        for lst in self.open_by_cust.values():
            lst.sort(key=lambda x: (x.due, x.id))
        self.free: set[int] = {i.id for i in invoices if i.status == "open"}
        self.paid = [i for i in invoices if i.status == "paid"]

    def free_of(self, cid: int) -> list[Inv]:
        return [i for i in self.open_by_cust[cid] if i.id in self.free]

    def take(self, *ids: int) -> None:
        for i in ids:
            assert i in self.free, i
            self.free.remove(i)


PURPOSE_A = ["{ref}", "Zahlung {ref}", "Rechnung {ref}", "{ref} Danke", "Ausgleich {ref}", "KD-{cid:05d} {ref}",
             "{ref} vom {due}", "Rg {ref}", "Ihre Rechnung {ref}", "{ref} / Skonto geprueft", "Zahlung {ref} {remit}"]
PURPOSE_NOTOK = ["Rechnung August", "Zahlung", "Ueberweisung", "Ausgleich offene Posten", "Rg. vom {d}",
                 "Abschlag", "Zahlung laut Kontoauszug", "Sammelueberweisung", "Rechnungen Juli/August",
                 "Monatsrechnung", "Ausgleich Konto", "Vielen Dank"]
NOISE_PURPOSE = ["Miete August", "Rueckzahlung Darlehen", "Spende", "Privat", "Erstattung", "Provision Q3",
                 "Umbuchung", "Ausgleich", "Zinsen", "Gutschrift"]


def fmt_ref_for_purpose(rng: random.Random, seq: int) -> str:
    r = rng.random()
    if r < 0.55:
        return f"RE-2026-{seq:06d}"
    if r < 0.65:
        return f"RE 2026 {seq:06d}"
    if r < 0.75:
        return f"RE-2026-{seq}"
    if r < 0.83:
        return f"RE/2026/{seq:06d}"
    if r < 0.90:
        return f"re-2026-{seq:06d}"
    if r < 0.95:
        return f"RE2026-{seq:06d}"
    return f"RE 2026/{seq:06d}"


def mangle(rng: random.Random, seq: int) -> str | None:
    """Return a mangled reference with normalised distance 1..2 to the real one, or None."""
    real = norm(f"RE-2026-{seq:06d}")
    digits = f"{seq:06d}"
    kind = rng.choice(["sub", "drop", "swap", "sub2", "nohyphen", "letter"])
    if kind == "sub":
        p = rng.randrange(6)
        d = list(digits)
        d[p] = rng.choice([c for c in "0123456789" if c != d[p]])
        cand = f"RE-2026-{''.join(d)}"
    elif kind == "drop":
        p = rng.randrange(6)
        cand = f"RE-2026-{digits[:p] + digits[p + 1:]}"
    elif kind == "swap":
        p = rng.randrange(5)
        if digits[p] == digits[p + 1]:
            return None
        d = list(digits)
        d[p], d[p + 1] = d[p + 1], d[p]
        cand = f"RE-2026-{''.join(d)}"
    elif kind == "sub2":
        p, q = rng.sample(range(6), 2)
        d = list(digits)
        d[p] = rng.choice([c for c in "0123456789" if c != d[p]])
        d[q] = rng.choice([c for c in "0123456789" if c != d[q]])
        cand = f"RE-2026-{''.join(d)}"
    elif kind == "nohyphen":
        cand = f"RE-2026{digits}"
    else:
        cand = rng.choice(["RF", "RR", "RE-", "R"]) + f"-2026-{digits}"
        cand = cand.replace("--", "-")
    toks = tokens_of(cand)
    if len(toks) != 1:
        return None
    d = lev(toks[0], real)
    if not 1 <= d <= FUZZY_K:
        return None
    return cand


def pick_remitter(rng: random.Random, c: Cust) -> str:
    name = rng.choice([c.legal, c.legal, *c.aliases])
    r = rng.random()
    if r < 0.15:
        return name.upper()
    if r < 0.30:
        return name.translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "AE", "Ö": "OE", "Ü": "UE", "ß": "ss"}))
    return name


def unknown_iban(rng: random.Random, known: set[str]) -> str:
    while True:
        body = f"DE{rng.randint(10, 99)}{rng.randint(10000000, 99999999)}{rng.randint(0, 9999999999):010d}"
        if body not in known:
            return body


def generate_statement(
    rng: random.Random,
    pool: Pool,
    custs: list[Cust],
    dup_pairs: dict[int, list[int]],
    days: list[date],
    prefix: str,
    counts: dict[str, int],
) -> list[Line]:
    known_ibans = {norm_iban(i) for c in custs for i in c.ibans}
    lines: list[Line] = []
    cust_by_id = {c.cid: c for c in custs}
    weights = [max(1, len(pool.free_of(c.cid))) for c in custs]

    def rnd_day() -> date:
        return rng.choice(days)

    def any_cust_with_free(min_free: int = 1) -> Cust:
        while True:
            c = rng.choices(custs, weights=weights)[0]
            if len(pool.free_of(c.cid)) >= min_free:
                return c

    def cust_iban(c: Cust) -> str:
        return rng.choice(c.ibans)

    def add(line: Line) -> None:
        lines.append(line)

    def purpose_with_ref(c: Cust, inv: Inv, ref: str) -> str:
        tpl = rng.choice(PURPOSE_A)
        return tpl.format(ref=ref, cid=c.cid, due=inv.due.strftime("%d.%m.%Y"), remit=c.legal.split()[0])

    # --- A1 -----------------------------------------------------------------
    for k in range(counts["A1"]):
        c = any_cust_with_free()
        inv = rng.choice(pool.free_of(c.cid))
        pool.take(inv.id)
        amt = inv.amount + (rng.choice([-1, 1]) if rng.random() < 0.02 else 0)
        iban = cust_iban(c) if rng.random() < 0.8 else (unknown_iban(rng, known_ibans) if rng.random() < 0.7 else "")
        day = rnd_day()
        add(Line(day, day + timedelta(days=rng.choice([0, 0, 1])), pick_remitter(rng, c), iban,
                 purpose_with_ref(c, inv, fmt_ref_for_purpose(rng, inv.id)), amt,
                 {"rule": "A1", "ids": [inv.id]}, "a1"))

    # --- A2 -----------------------------------------------------------------
    n_a2 = 0
    while n_a2 < counts["A2"]:
        c = any_cust_with_free()
        inv = rng.choice(pool.free_of(c.cid))
        m = mangle(rng, inv.id)
        if m is None:
            continue
        pool.take(inv.id)
        unknown = rng.random() < 0.25
        iban = (unknown_iban(rng, known_ibans) if rng.random() < 0.7 else "") if unknown else cust_iban(c)
        day = rnd_day()
        add(Line(day, day, pick_remitter(rng, c), iban, purpose_with_ref(c, inv, m), inv.amount,
                 {"rule": "A2", "ids": [inv.id]}, "a2_unknown_iban" if unknown else "a2"))
        n_a2 += 1

    # --- B1 -----------------------------------------------------------------
    n_b1 = 0
    while n_b1 < counts["B1"]:
        c = any_cust_with_free()
        inv = rng.choice(pool.free_of(c.cid))
        if c.cid in dup_pairs and inv.id in dup_pairs[c.cid]:
            continue
        n_b1 += 1
        pool.take(inv.id)
        amt = inv.amount + (rng.choice([-1, 1]) if rng.random() < 0.03 else 0)
        day = rnd_day()
        add(Line(day, day, pick_remitter(rng, c), cust_iban(c),
                 rng.choice(PURPOSE_NOTOK).format(d=inv.due.strftime("%d.%m.%Y")), amt,
                 {"rule": "B1", "ids": [inv.id]}, "b1"))

    # --- order conflicts (B1, duplicate amounts, late booking) -----------------
    pairs = [(cid, ids) for cid, ids in dup_pairs.items() if all(i in pool.free for i in ids)]
    rng.shuffle(pairs)
    for cid, (first_id, second_id) in pairs[: counts["conflict_pairs"]]:
        c = cust_by_id[cid]
        pool.take(first_id, second_id)
        amt = pool.inv[first_id].amount
        idx = rng.randint(3, len(days) - 1)
        normal_day, late_day = days[idx], days[rng.randint(0, idx - 1)]
        add(Line(normal_day, normal_day, pick_remitter(rng, c), cust_iban(c), "Rechnung", amt,
                 {"rule": "B1", "ids": [second_id]}, "order_conflict"))
        add(Line(late_day, normal_day, pick_remitter(rng, c), cust_iban(c), "Rechnung", amt,
                 {"rule": "B1", "ids": [first_id]}, "order_conflict", late=True))

    # --- B2 -----------------------------------------------------------------
    n_b2 = 0
    lo_day, hi_day = min(days) - timedelta(days=B2_WINDOW), max(days) + timedelta(days=B2_WINDOW)
    while n_b2 < counts["B2"]:
        c = any_cust_with_free()
        if c.cid in (custs[10].cid, custs[11].cid):
            continue
        cands = [i for i in pool.free_of(c.cid) if lo_day <= i.due <= hi_day]
        if not cands:
            continue
        inv = rng.choice(cands)
        pool.take(inv.id)
        okdays = [d for d in days if abs((inv.due - d).days) <= B2_WINDOW]
        day = rng.choice(okdays)
        iban = unknown_iban(rng, known_ibans) if rng.random() < 0.6 else ""
        add(Line(day, day, pick_remitter(rng, c), iban, rng.choice(PURPOSE_NOTOK).format(d=inv.due.strftime("%d.%m.%Y")),
                 inv.amount, {"rule": "B2", "ids": [inv.id]}, "b2"))
        n_b2 += 1

    # --- B2 window traps: same as B2 but booking > 14 days from due -----------
    n = 0
    while n < counts["b2_trap"]:
        c = any_cust_with_free()
        if c.cid in (custs[10].cid, custs[11].cid):
            continue
        cands = [i for i in pool.free_of(c.cid) if any(B2_WINDOW < abs((i.due - d).days) <= 45 for d in days)]
        if not cands:
            continue
        inv = rng.choice(cands)
        pool.take(inv.id)
        day = rng.choice([d for d in days if B2_WINDOW < abs((inv.due - d).days) <= 45])
        add(Line(day, day, pick_remitter(rng, c), "", "Zahlung", inv.amount, {"reason": "NO_CANDIDATE"}, "b2_window_trap"))
        n += 1

    # --- B3 -----------------------------------------------------------------
    def batch_line(c: Cust, run: list[Inv], tag: str, iban_known: bool = True) -> None:
        pool.take(*[i.id for i in run])
        total = sum(i.amount for i in run)
        day = rnd_day()
        iban = cust_iban(c) if iban_known else ""
        add(Line(day, day, pick_remitter(rng, c), iban, rng.choice(["Sammelueberweisung", "Rechnungen Juli/August",
                 "Ausgleich offene Posten", "Zahlung laut Kontoauszug"]), total, {"rule": "B3", "ids": [i.id for i in run]}, tag))

    def contiguous_runs(c: Cust, min_len: int, max_len: int) -> list[list[Inv]]:
        """Runs contiguous in the customer's full open list whose members are all free."""
        full = pool.open_by_cust[c.cid]
        runs = []
        for i in range(len(full)):
            for j in range(i + min_len - 1, min(len(full), i + max_len)):
                if (full[j].due - full[i].due).days > B3_WINDOW:
                    break
                seg = full[i : j + 1]
                if all(x.id in pool.free for x in seg):
                    runs.append(seg)
        return runs

    # large customers (>12 open) — the PR-418 cap victims
    large = [c for c in custs if len(pool.open_by_cust[c.cid]) > 12]
    rng.shuffle(large)
    n = 0
    for c in large:
        if n >= counts["B3_large"]:
            break
        runs = contiguous_runs(c, 3, 25)
        long_runs = [r for r in runs if len(r) >= 12]
        if n < 3 and long_runs:
            batch_line(c, rng.choice(long_runs), "b3_large")
        elif runs:
            batch_line(c, rng.choice(runs), "b3_large")
        else:
            continue
        n += 1
    assert n == counts["B3_large"], n

    # small customers (<= 12 open)
    small = [c for c in custs if 3 <= len(pool.open_by_cust[c.cid]) <= 12]
    rng.shuffle(small)
    n = 0
    for c in small:
        if n >= counts["B3_small"]:
            break
        runs = contiguous_runs(c, 2, 6)
        if not runs:
            continue
        batch_line(c, rng.choice(runs), "b3_small", iban_known=rng.random() < 0.85)
        n += 1
    assert n == counts["B3_small"], n

    # B3 window traps: contiguous, right sum, but spanning > 60 days
    n = 0
    for c in rng.sample(custs, len(custs)):
        if n >= counts["b3_window_trap"]:
            break
        full = pool.open_by_cust[c.cid]
        found = None
        for i in range(len(full)):
            for j in range(i + 1, min(len(full), i + 6)):
                seg = full[i : j + 1]
                if (seg[-1].due - seg[0].due).days > B3_WINDOW + 5 and all(x.id in pool.free for x in seg):
                    found = seg
                    break
            if found:
                break
        if not found:
            continue
        pool.take(*[x.id for x in found])  # keep them out of other lines
        day = rnd_day()
        add(Line(day, day, pick_remitter(rng, c), cust_iban(c), "Sammelueberweisung", sum(x.amount for x in found),
                 {"reason": "NO_CANDIDATE"}, "b3_window_trap"))
        n += 1

    # --- noise ----------------------------------------------------------------
    for k in range(counts["debit"]):
        day = rnd_day()
        add(Line(day, day, rng.choice(["Nordwind Bank AG", "Kartenservice", "Bundesagentur"]), "",
                 rng.choice(["Kontofuehrungsgebuehr", "Ruecklastschrift", "Entgelt Auslandsueberweisung", "Zinsabschluss"]),
                 -rng.randint(90, 45000), {"reason": "DEBIT"}, "debit"))
    for k in range(counts["unknown"]):
        day = rnd_day()
        nm = f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)}"
        purpose = rng.choice(NOISE_PURPOSE)
        if rng.random() < 0.15:  # a reference-looking token that names no invoice
            purpose += f" RE-2026-{rng.randint(60000, 99999):06d}"
        add(Line(day, day, nm, unknown_iban(rng, known_ibans) if rng.random() < 0.8 else "", purpose,
                 rand_amount(rng), {"reason": "NO_CANDIDATE"}, "unknown_remitter"))
    for k in range(counts["dup_paid"]):
        inv = rng.choice(pool.paid)
        c = cust_by_id[inv.cid]
        day = rnd_day()
        add(Line(day, day, pick_remitter(rng, c), cust_iban(c), purpose_with_ref(c, inv, fmt_ref_for_purpose(rng, inv.id)),
                 inv.amount, {"reason": "INVOICE_CONSUMED"}, "duplicate_payment"))
    for k in range(counts["partial"]):
        c = any_cust_with_free()
        inv = rng.choice(pool.free_of(c.cid))
        pool.take(inv.id)
        day = rnd_day()
        amt = inv.amount // 2 if rng.random() < 0.7 else inv.amount - rng.randint(3, 300)
        with_tok = rng.random() < 0.4
        purpose = purpose_with_ref(c, inv, f"RE-2026-{inv.id:06d}") if with_tok else rng.choice(PURPOSE_NOTOK).format(d="01.08.2026")
        add(Line(day, day, pick_remitter(rng, c), cust_iban(c), purpose, amt, {"reason": "NO_CANDIDATE"}, "partial_payment"))
    n_amb = 0
    while n_amb < counts["ambiguous_name"]:
        c = rng.choice([custs[10], custs[11]])
        free = pool.free_of(c.cid)
        if not free:
            continue
        n_amb += 1
        inv = rng.choice(free)
        pool.take(inv.id)
        day = rnd_day()
        add(Line(day, day, "Nordwind Handel Nord", "", "Zahlung", inv.amount, {"reason": "NO_CANDIDATE"}, "ambiguous_name"))

    # --- ordering: file order = booking date, late bookings appended ------------
    normal = [ln for ln in lines if not ln.late]
    late = [ln for ln in lines if ln.late]
    extra_late = rng.sample(normal, counts["extra_late"])
    for ln in extra_late:
        ln.late = True
    normal = [ln for ln in lines if not ln.late]
    late = [ln for ln in lines if ln.late]
    rng.shuffle(normal)
    normal.sort(key=lambda ln: ln.booking)
    rng.shuffle(late)
    ordered = normal + late
    for n, ln in enumerate(ordered, start=1):
        ln.line_id = f"{prefix}{n:06d}"
    return ordered


# --------------------------------------------------------------------------- #
# Oracle: straightforward implementation of docs/matching_rules.md
# --------------------------------------------------------------------------- #
def oracle(lines: list[Line], invoices: list[Inv], custs: list[Cust]) -> dict[str, dict]:
    norm_of = {i.id: norm(i.reference) for i in invoices}
    by_norm: dict[str, Inv] = {}
    for i in invoices:
        if i.status == "open":
            assert norm_of[i.id] not in by_norm, "normalised references must be unique"
            by_norm[norm_of[i.id]] = i
    paid_norms = {norm_of[i.id] for i in invoices if i.status != "open"}
    by_amount: dict[int, list[Inv]] = defaultdict(list)
    by_cust: dict[int, list[Inv]] = defaultdict(list)
    for i in invoices:
        if i.status == "open":
            by_amount[i.amount].append(i)
            by_cust[i.cid].append(i)
    for lst in by_cust.values():
        lst.sort(key=lambda x: (x.due, x.id))
    iban_map = {norm_iban(ib): c.cid for c in custs for ib in c.ibans}
    name_count: dict[str, set[int]] = defaultdict(set)
    for c in custs:
        for nm in [c.legal, *c.aliases]:
            name_count[norm(nm)].add(c.cid)
    name_map = {k: next(iter(v)) for k, v in name_count.items() if len(v) == 1}

    consumed: set[int] = set()
    out: dict[str, dict] = {}

    def avail(i: Inv) -> bool:
        return i.status == "open" and i.id not in consumed

    def pick(cands):  # list of (amount_diff, dist, inv)
        return min(cands, key=lambda t: (t[0], t[1], t[2].due, t[2].id))[2]

    for ln in sorted(lines, key=lambda l: (l.booking, l.line_id)):
        if ln.amount <= 0:
            out[ln.line_id] = {"reason": "DEBIT"}
            continue
        toks = tokens_of(ln.purpose)
        chosen: list[Inv] | None = None
        rule = None
        # A1
        c = []
        for t in toks:
            i = by_norm.get(t)
            if i and avail(i) and abs(i.amount - ln.amount) <= TOL:
                c.append((abs(i.amount - ln.amount), 0, i))
        if c:
            chosen, rule = [pick(c)], "A1"
        # A2
        if chosen is None and toks:
            c = []
            for cents in range(ln.amount - TOL, ln.amount + TOL + 1):
                for i in by_amount.get(cents, []):
                    if not avail(i):
                        continue
                    d = min(lev(t, norm_of[i.id]) for t in toks)
                    if d <= FUZZY_K:
                        c.append((abs(i.amount - ln.amount), d, i))
            if c:
                chosen, rule = [pick(c)], "A2"
        cid_iban = iban_map.get(norm_iban(ln.iban)) if ln.iban else None
        cid_name = name_map.get(norm(ln.remitter)) if ln.remitter else None
        # B1
        if chosen is None and cid_iban is not None:
            c = [(abs(i.amount - ln.amount), 0, i) for i in by_cust[cid_iban] if avail(i) and abs(i.amount - ln.amount) <= TOL]
            if c:
                chosen, rule = [pick(c)], "B1"
        # B2
        if chosen is None and cid_name is not None:
            c = [(abs(i.amount - ln.amount), 0, i) for i in by_cust[cid_name]
                 if avail(i) and abs(i.amount - ln.amount) <= TOL and abs((i.due - ln.booking).days) <= B2_WINDOW]
            if c:
                chosen, rule = [pick(c)], "B2"
        # B3
        cid3 = cid_iban if cid_iban is not None else cid_name
        if chosen is None and cid3 is not None:
            seq = [i for i in by_cust[cid3] if avail(i)]
            best = None
            for i in range(len(seq)):
                for j in range(i + B3_MIN - 1, min(len(seq), i + B3_MAX)):
                    if (seq[j].due - seq[i].due).days > B3_WINDOW:
                        continue
                    s = sum(x.amount for x in seq[i : j + 1])
                    if abs(s - ln.amount) <= TOL:
                        key = (i, j - i)
                        if best is None or key < best[0]:
                            best = (key, seq[i : j + 1])
            if best:
                chosen, rule = best[1], "B3"
        if chosen:
            consumed.update(i.id for i in chosen)
            out[ln.line_id] = {"rule": rule, "invoice_ids": sorted(i.id for i in chosen)}
        else:
            unavailable = any(t in paid_norms or (t in by_norm and by_norm[t].id in consumed) for t in toks)
            out[ln.line_id] = {"reason": "INVOICE_CONSUMED" if unavailable else "NO_CANDIDATE"}
    return out


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #
def write_customers(custs: list[Cust], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["customer_id", "legal_name", "aliases", "ibans"])
        for c in custs:
            w.writerow([c.cid, c.legal, "|".join(c.aliases), "|".join(c.ibans)])


def write_invoices(invoices: list[Inv], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["id", "customer_id", "reference", "amount_cents", "currency", "due_date", "status"])
        for i in invoices:
            w.writerow([i.id, i.cid, i.reference, i.amount, "EUR", i.due.isoformat(), i.status])


def write_statement(lines: list[Line], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";", lineterminator="\n")
        w.writerow(["Umsatz-ID", "Buchungstag", "Valutadatum", "Auftraggeber", "IBAN", "Verwendungszweck", "Betrag", "Waehrung"])
        for ln in lines:
            w.writerow([ln.line_id, ln.booking.strftime("%d.%m.%Y"), ln.value.strftime("%d.%m.%Y"), ln.remitter, ln.iban,
                        ln.purpose, fmt_amount_de(ln.amount), "EUR"])


def ground_truth(lines: list[Line], truth: dict[str, dict], invoices: list[Inv]) -> dict:
    tags: dict[str, list[str]] = defaultdict(list)
    for ln in lines:
        tags[ln.tag].append(ln.line_id)
    open_count = defaultdict(int)
    for i in invoices:
        if i.status == "open":
            open_count[i.cid] += 1
    matched = [t for t in truth.values() if "rule" in t]
    by_rule = defaultdict(int)
    for t in matched:
        by_rule[t["rule"]] += 1
    by_reason = defaultdict(int)
    for t in truth.values():
        if "reason" in t:
            by_reason[t["reason"]] += 1
    amount_of = {ln.line_id: ln.amount for ln in lines}
    return {
        "lines": truth,
        "tags": {k: sorted(v) for k, v in tags.items()},
        "summary": {
            "lines": len(lines),
            "matched_lines": len(matched),
            "unmatched_lines": len(lines) - len(matched),
            "matched_invoices": sum(len(t["invoice_ids"]) for t in matched),
            "matched_amount_cents": sum(amount_of[lid] for lid, t in truth.items() if "rule" in t),
            "by_rule": dict(by_rule),
            "unmatched_by_reason": dict(by_reason),
        },
        "large_customer_batches": sorted(
            lid for lid, t in truth.items()
            if t.get("rule") == "B3" and open_count[next(i.cid for i in invoices if i.id == t["invoice_ids"][0])] > 12
        ),
    }


def check_intent(lines: list[Line], truth: dict[str, dict]) -> None:
    mism = defaultdict(list)
    for ln in lines:
        t = truth[ln.line_id]
        if "rule" in ln.intent:
            ok = t.get("rule") == ln.intent["rule"] and t.get("invoice_ids") == sorted(ln.intent["ids"])
        else:
            ok = t.get("reason") == ln.intent["reason"]
        if not ok:
            mism[ln.tag].append((ln.line_id, ln.intent, t, ln.purpose, ln.amount))
    total = sum(len(v) for v in mism.values())
    print(f"  intent/oracle disagreements: {total} of {len(lines)}")
    for tag, items in mism.items():
        print(f"    {tag}: {len(items)}")
        for it in items[:3]:
            print("      ", it)
    strict = {"order_conflict", "b3_large", "b3_small", "b3_window_trap", "b2_window_trap", "a2_unknown_iban",
              "ambiguous_name", "debit", "duplicate_payment"}
    bad = {k: v for k, v in mism.items() if k in strict}
    if bad:
        raise SystemExit(f"oracle disagrees with constructed scenarios: { {k: len(v) for k, v in bad.items()} }")
    if total > 0.005 * len(lines):
        raise SystemExit("too many unintended lines")


def main() -> None:
    rng = random.Random(2291)
    custs = make_customers(rng, 3000)
    invoices, dup_pairs = make_invoices(rng, custs)
    print(f"customers={len(custs)} invoices={len(invoices)} open={sum(i.status == 'open' for i in invoices)} dup_pairs={len(dup_pairs)}")
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "statements").mkdir(exist_ok=True)
    write_customers(custs, DATA / "customers.csv")
    write_invoices(invoices, DATA / "invoices.csv")

    # full August statement --------------------------------------------------
    full_counts = dict(A2=1800, B1=1200, conflict_pairs=30, B2=600, b2_trap=15, B3_large=17, B3_small=340,
                       b3_window_trap=10, debit=120, unknown=600, dup_paid=200, partial=400, ambiguous_name=6,
                       extra_late=110)
    fixed = sum(v for k, v in full_counts.items() if k not in ("conflict_pairs", "extra_late")) + 2 * full_counts["conflict_pairs"]
    full_counts["A1"] = 12000 - fixed
    pool = Pool(invoices, custs)
    rng_full = random.Random(20260831)
    full = generate_statement(rng_full, pool, custs, dup_pairs, biz_days(2026, 8), "NW-2026-08-", full_counts)
    assert len(full) == 12000, len(full)
    truth_full = oracle(full, invoices, custs)
    print("full statement:")
    check_intent(full, truth_full)
    write_statement(full, DATA / "statements" / "nordwind_2026-08.csv")
    gt = ground_truth(full, truth_full, invoices)
    # expectation for running the same statement again on the already-reconciled ledger
    matched_ids = {i for t in truth_full.values() if "rule" in t for i in t["invoice_ids"]}
    inv_after = [Inv(i.id, i.cid, i.reference, i.amount, i.due, "paid" if i.id in matched_ids else i.status) for i in invoices]
    gt["rerun_on_same_db"] = ground_truth(full, oracle(full, inv_after, custs), inv_after)["summary"]
    print("  rerun summary:", json.dumps(gt["rerun_on_same_db"]))
    print("  summary:", json.dumps(gt["summary"]))
    print("  large-customer batches:", len(gt["large_customer_batches"]))
    (HERE / "ground_truth_full.json").write_text(json.dumps(gt, indent=1, sort_keys=True) + "\n")

    # sample_200: first 200 rows of the full file ------------------------------
    sample = full[:200]
    write_statement(sample, DATA / "statements" / "sample_200.csv")
    truth_sample = oracle(sample, invoices, custs)
    gts = ground_truth(sample, truth_sample, invoices)
    print("sample_200 summary:", json.dumps(gts["summary"]))
    (HERE / "ground_truth_sample200.json").write_text(json.dumps(gts, indent=1, sort_keys=True) + "\n")

    # hidden alternative statement (September, different seed, same ledger) ----
    alt_counts = dict(A2=220, B1=150, conflict_pairs=8, B2=80, b2_trap=4, B3_large=6, B3_small=40,
                      b3_window_trap=3, debit=15, unknown=80, dup_paid=25, partial=50, ambiguous_name=2, extra_late=15)
    fixed = sum(v for k, v in alt_counts.items() if k not in ("conflict_pairs", "extra_late")) + 2 * alt_counts["conflict_pairs"]
    alt_counts["A1"] = 1500 - fixed
    pool2 = Pool(invoices, custs)
    rng_alt = random.Random(20260930)
    alt = generate_statement(rng_alt, pool2, custs, dup_pairs, biz_days(2026, 9), "NW-2026-09-", alt_counts)
    assert len(alt) == 1500, len(alt)
    truth_alt = oracle(alt, invoices, custs)
    print("alt statement:")
    check_intent(alt, truth_alt)
    write_statement(alt, HERE / "alt_statement_2026-09.csv")
    gta = ground_truth(alt, truth_alt, invoices)
    print("  summary:", json.dumps(gta["summary"]))
    (HERE / "ground_truth_alt.json").write_text(json.dumps(gta, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
