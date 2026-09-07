#!/usr/bin/env bash
# Reference fix for INCIDENT-2291: bulk-load and index the ledger once per run, bounded
# edit distance on amount-filtered candidates, one SQLite connection with bulk writes,
# schema v2 (stored normalised reference + indexes, automatic idempotent migration),
# customer master indexed once, and rule B3 as the contiguous oldest-first run scan the
# specification defines (removing the PR-418 subset cap).
set -euo pipefail
cd /app

mkdir -p "$(dirname recon/config.py)"
cat > recon/config.py <<'RECON_EOF_00'
"""Matching parameters (docs/matching_rules.md section 9).

Changes to these values require Finance Operations sign-off.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MatchConfig:
    amount_tolerance_cents: int = 1
    fuzzy_max_distance: int = 2
    b2_window_days: int = 14
    batch_window_days: int = 60
    batch_max_run: int = 40
    batch_min_run: int = 2


DEFAULT_CONFIG = MatchConfig()
RECON_EOF_00

mkdir -p "$(dirname recon/matching/normalize.py)"
cat > recon/matching/normalize.py <<'RECON_EOF_01'
"""Text normalisation and reference-token extraction (matching_rules.md section 1).

This module is the single normaliser used by the matcher, the ops `lookup`
command and the schema backfill; nothing else may re-implement these rules.
"""
from __future__ import annotations

import re
from functools import lru_cache

_TRANSLIT = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "AE", "Ö": "OE", "Ü": "UE", "ß": "ss"}
)
_DIGIT_RUN = re.compile(r"[0-9]+")
_NON_ALNUM = re.compile(r"[^A-Z0-9]")
# Section 1.2: 1-3 letters, optional separator, four digits, optional separator, 1-8 digits.
_TOKEN = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{1,3}[ \-/.]?[0-9]{4}[ \-/.]?[0-9]{1,8}(?![0-9])")


def _strip_leading_zeros(match: re.Match) -> str:
    return match.group(0).lstrip("0") or "0"


@lru_cache(maxsize=262_144)
def normalize_reference(text: str) -> str:
    """Apply the four normalisation steps of section 1.1, in order."""
    text = text.translate(_TRANSLIT).upper()
    text = _DIGIT_RUN.sub(_strip_leading_zeros, text)
    return _NON_ALNUM.sub("", text)


def extract_reference_tokens(purpose: str) -> list[str]:
    """Distinct normalised reference tokens of a purpose text, in order of appearance."""
    tokens: list[str] = []
    for match in _TOKEN.finditer(purpose):
        norm = normalize_reference(match.group(0))
        if norm not in tokens:
            tokens.append(norm)
    return tokens


def normalize_iban(iban: str) -> str:
    return "".join(iban.split()).upper()
RECON_EOF_01

mkdir -p "$(dirname recon/matching/fuzzy.py)"
cat > recon/matching/fuzzy.py <<'RECON_EOF_02'
"""Edit distance for rule A2.

`levenshtein` is the plain textbook distance (kept for tooling and tests);
`bounded_distance` is what the matcher uses: it answers "is the distance at
most k, and if so what is it" and gives up as early as the band allows.
"""
from __future__ import annotations


def levenshtein(a: str, b: str) -> int:
    """Unit-cost Levenshtein distance, two-row dynamic programme."""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def bounded_distance(a: str, b: str, k: int) -> int | None:
    """Return the Levenshtein distance of ``a`` and ``b`` if it is <= k, else None.

    Only the diagonal band of width 2k+1 is evaluated and the scan stops as soon
    as every cell of a row exceeds k.
    """
    if abs(len(a) - len(b)) > k:
        return None
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    n = len(b)
    if n == 0:
        return len(a) if len(a) <= k else None
    inf = k + 1
    prev = list(range(n + 1))
    for i in range(1, len(a) + 1):
        lo = max(1, i - k)
        hi = min(n, i + k)
        cur = [inf] * (n + 1)
        if lo == 1:
            cur[0] = i if i <= k else inf
        ca = a[i - 1]
        best = cur[0]
        for j in range(lo, hi + 1):
            v = prev[j] + 1
            left = cur[j - 1] + 1
            if left < v:
                v = left
            diag = prev[j - 1] + (ca != b[j - 1])
            if diag < v:
                v = diag
            cur[j] = v
            if v < best:
                best = v
        if best > k:
            return None
        prev = cur
    d = prev[n]
    return d if d <= k else None
RECON_EOF_02

mkdir -p "$(dirname recon/matching/batch.py)"
cat > recon/matching/batch.py <<'RECON_EOF_03'
"""Rule B3 — batch payments (matching_rules.md section 4, B3).

A run is a *contiguous* slice of the customer's available invoices in
(due_date, id) order whose amounts sum to the payment, spans at most the
configured window and has between min and max invoices. Earliest start wins,
then the shortest run.
"""
from __future__ import annotations

from typing import Sequence

from recon.config import DEFAULT_CONFIG, MatchConfig
from recon.models import Invoice


def oldest_first(invoices: Sequence[Invoice]) -> list[Invoice]:
    return sorted(invoices, key=lambda inv: (inv.due_date, inv.id))


def find_batch(
    invoices: Sequence[Invoice], amount_cents: int, config: MatchConfig = DEFAULT_CONFIG
) -> list[Invoice] | None:
    """Return the winning run for ``amount_cents`` or None. Linear in runs, not subsets."""
    invs = oldest_first(invoices)
    n = len(invs)
    if n < config.batch_min_run:
        return None
    tol = config.amount_tolerance_cents
    prefix = [0] * (n + 1)
    for idx, inv in enumerate(invs):
        prefix[idx + 1] = prefix[idx] + inv.amount_cents
    upper = amount_cents + tol
    for i in range(n - config.batch_min_run + 1):
        start_due = invs[i].due_date
        last = min(n, i + config.batch_max_run)
        for j in range(i + config.batch_min_run - 1, last):
            if (invs[j].due_date - start_due).days > config.batch_window_days:
                break
            total = prefix[j + 1] - prefix[i]
            if total > upper:
                break  # amounts are positive: longer runs only grow
            if abs(total - amount_cents) <= tol:
                return invs[i : j + 1]
    return None
RECON_EOF_03

mkdir -p "$(dirname recon/matching/candidates.py)"
cat > recon/matching/candidates.py <<'RECON_EOF_04'
"""Candidate generation for rules A1, A2, B1, B2, B3 (matching_rules.md section 4).

All lookups go through `InvoiceIndex`, which is built once per run from the
bulk-loaded ledger and keeps track of consumed invoices (section 6).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Sequence

from recon.config import DEFAULT_CONFIG, MatchConfig
from recon.customers.master import CustomerIndex
from recon.matching import batch
from recon.matching.fuzzy import bounded_distance
from recon.matching.normalize import normalize_reference
from recon.models import Candidate, Customer, Invoice, StatementLine

RULES: tuple[str, ...] = ("A1", "A2", "B1", "B2", "B3")


class InvoiceIndex:
    """In-memory indexes over the ledger: by normalised reference, customer and amount."""

    def __init__(self, invoices: Iterable[Invoice]):
        self._by_norm: dict[str, list[Invoice]] = defaultdict(list)
        self._by_customer: dict[int, list[Invoice]] = defaultdict(list)
        self._by_amount: dict[int, list[Invoice]] = defaultdict(list)
        self._norms_not_open: set[str] = set()
        self._consumed: set[int] = set()
        self.open_count = 0
        for inv in invoices:
            norm = normalize_reference(inv.reference)
            if not inv.is_open:
                self._norms_not_open.add(norm)
                continue
            self.open_count += 1
            self._by_norm[norm].append(inv)
            self._by_customer[inv.customer_id].append(inv)
            self._by_amount[inv.amount_cents].append(inv)
        for lst in self._by_customer.values():
            lst.sort(key=lambda inv: (inv.due_date, inv.id))

    # -- availability --------------------------------------------------------
    def is_available(self, inv: Invoice) -> bool:
        return inv.id not in self._consumed

    def consume(self, invoices: Iterable[Invoice]) -> None:
        for inv in invoices:
            self._consumed.add(inv.id)
            self._norms_not_open.add(normalize_reference(inv.reference))

    def reference_unavailable(self, norm: str) -> bool:
        """True when ``norm`` names an invoice that is paid or already consumed (section 7)."""
        return norm in self._norms_not_open

    # -- lookups ---------------------------------------------------------------
    def by_reference(self, norm: str) -> list[Invoice]:
        return [inv for inv in self._by_norm.get(norm, ()) if self.is_available(inv)]

    def by_amount(self, amount_cents: int, tolerance: int) -> list[Invoice]:
        out: list[Invoice] = []
        for cents in range(amount_cents - tolerance, amount_cents + tolerance + 1):
            out.extend(inv for inv in self._by_amount.get(cents, ()) if self.is_available(inv))
        return out

    def open_for_customer(self, customer_id: int) -> list[Invoice]:
        return [inv for inv in self._by_customer.get(customer_id, ()) if self.is_available(inv)]

    def open_invoice_count(self, customer_id: int) -> int:
        return len(self.open_for_customer(customer_id))


def _amount_ok(a: int, b: int, config: MatchConfig) -> bool:
    return abs(a - b) <= config.amount_tolerance_cents


def rule_a1(line: StatementLine, tokens: Sequence[str], index: InvoiceIndex, config: MatchConfig) -> list[Candidate]:
    out = []
    for tok in tokens:
        for inv in index.by_reference(tok):
            if _amount_ok(inv.amount_cents, line.amount_cents, config):
                out.append(Candidate("A1", (inv,), abs(inv.amount_cents - line.amount_cents), 0))
    return out


def rule_a2(line: StatementLine, tokens: Sequence[str], index: InvoiceIndex, config: MatchConfig) -> list[Candidate]:
    if not tokens:
        return []
    out = []
    k = config.fuzzy_max_distance
    for inv in index.by_amount(line.amount_cents, config.amount_tolerance_cents):
        norm = normalize_reference(inv.reference)
        best = None
        for tok in tokens:
            d = bounded_distance(tok, norm, k)
            if d is not None and (best is None or d < best):
                best = d
        if best is not None:
            out.append(Candidate("A2", (inv,), abs(inv.amount_cents - line.amount_cents), best))
    return out


def rule_b1(line: StatementLine, customer: Customer | None, index: InvoiceIndex, config: MatchConfig) -> list[Candidate]:
    if customer is None:
        return []
    return [
        Candidate("B1", (inv,), abs(inv.amount_cents - line.amount_cents), 0)
        for inv in index.open_for_customer(customer.customer_id)
        if _amount_ok(inv.amount_cents, line.amount_cents, config)
    ]


def rule_b2(line: StatementLine, customer: Customer | None, index: InvoiceIndex, config: MatchConfig) -> list[Candidate]:
    if customer is None:
        return []
    return [
        Candidate("B2", (inv,), abs(inv.amount_cents - line.amount_cents), 0)
        for inv in index.open_for_customer(customer.customer_id)
        if _amount_ok(inv.amount_cents, line.amount_cents, config)
        and abs((inv.due_date - line.booking_date).days) <= config.b2_window_days
    ]


def rule_b3(line: StatementLine, customer: Customer | None, index: InvoiceIndex, config: MatchConfig) -> list[Candidate]:
    if customer is None:
        return []
    run = batch.find_batch(index.open_for_customer(customer.customer_id), line.amount_cents, config)
    if not run:
        return []
    total = sum(inv.amount_cents for inv in run)
    return [Candidate("B3", tuple(run), abs(total - line.amount_cents), 0)]


def find_candidates(
    line: StatementLine,
    tokens: Sequence[str],
    index: InvoiceIndex,
    customers: CustomerIndex,
    config: MatchConfig = DEFAULT_CONFIG,
) -> list[Candidate]:
    """Candidates of the first rule (in A1..B3 order) that produces any."""
    cands = rule_a1(line, tokens, index, config)
    if cands:
        return cands
    cands = rule_a2(line, tokens, index, config)
    if cands:
        return cands
    by_iban = customers.by_iban(line.iban)
    cands = rule_b1(line, by_iban, index, config)
    if cands:
        return cands
    by_name = customers.by_name(line.remitter)
    cands = rule_b2(line, by_name, index, config)
    if cands:
        return cands
    return rule_b3(line, by_iban or by_name, index, config)
RECON_EOF_04

mkdir -p "$(dirname recon/matching/decision.py)"
cat > recon/matching/decision.py <<'RECON_EOF_05'
"""Turn ranked candidates into a single MatchResult with a reason code (section 7)."""
from __future__ import annotations

from typing import Sequence

from recon.matching import scoring
from recon.matching.candidates import InvoiceIndex
from recon.models import Candidate, MatchResult, StatementLine

REASON_DEBIT = "DEBIT"
REASON_INVOICE_CONSUMED = "INVOICE_CONSUMED"
REASON_NO_CANDIDATE = "NO_CANDIDATE"
REASONS: tuple[str, ...] = (REASON_DEBIT, REASON_INVOICE_CONSUMED, REASON_NO_CANDIDATE)


def decide(
    line: StatementLine, tokens: Sequence[str], candidates: Sequence[Candidate], index: InvoiceIndex
) -> MatchResult:
    if not line.is_credit:
        return MatchResult(line=line, reason=REASON_DEBIT)
    chosen = scoring.best(candidates)
    if chosen is not None:
        return MatchResult(line=line, rule=chosen.rule, invoices=tuple(chosen.invoices))
    if any(index.reference_unavailable(tok) for tok in tokens):
        return MatchResult(line=line, reason=REASON_INVOICE_CONSUMED)
    return MatchResult(line=line, reason=REASON_NO_CANDIDATE)
RECON_EOF_05

mkdir -p "$(dirname recon/customers/master.py)"
cat > recon/customers/master.py <<'RECON_EOF_06'
"""Customer master (customers.csv) and the IBAN / name lookups of section 2.2.

customers.csv columns: customer_id,legal_name,aliases,ibans
  aliases and ibans are '|' separated lists.
"""
from __future__ import annotations

import csv
from pathlib import Path

from recon.matching.normalize import normalize_iban, normalize_reference
from recon.models import Customer


def load_customers(path: str | Path) -> list[Customer]:
    customers: list[Customer] = []
    with Path(path).open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            aliases = tuple(a.strip() for a in (row.get("aliases") or "").split("|") if a.strip())
            ibans = tuple(normalize_iban(i) for i in (row.get("ibans") or "").split("|") if i.strip())
            customers.append(
                Customer(
                    customer_id=int(row["customer_id"]),
                    legal_name=row["legal_name"].strip(),
                    aliases=aliases,
                    ibans=ibans,
                )
            )
    return customers


class CustomerIndex:
    """Lookups built once per run.

    A normalised name carried by more than one customer identifies nobody
    (section 2.2), so such names are dropped from the name index.
    """

    def __init__(self, customers: list[Customer]):
        self.by_id: dict[int, Customer] = {c.customer_id: c for c in customers}
        self._by_iban: dict[str, Customer] = {}
        by_name: dict[str, set[int]] = {}
        for cust in customers:
            for iban in cust.ibans:
                self._by_iban.setdefault(iban, cust)
            for name in cust.names:
                by_name.setdefault(normalize_reference(name), set()).add(cust.customer_id)
        self._by_name: dict[str, Customer] = {
            norm: self.by_id[next(iter(ids))] for norm, ids in by_name.items() if len(ids) == 1
        }

    def by_iban(self, iban: str) -> Customer | None:
        if not iban:
            return None
        return self._by_iban.get(normalize_iban(iban))

    def by_name(self, remitter: str) -> Customer | None:
        if not remitter:
            return None
        return self._by_name.get(normalize_reference(remitter))

    def __len__(self) -> int:
        return len(self.by_id)


def build_customer_index(path: str | Path) -> CustomerIndex:
    return CustomerIndex(load_customers(path))
RECON_EOF_06

mkdir -p "$(dirname recon/store/schema.sql)"
cat > recon/store/schema.sql <<'RECON_EOF_07'
-- recon ledger, schema version 1 (baseline). Later versions live in recon/store/migrations.py.

CREATE TABLE IF NOT EXISTS customers (
    customer_id  INTEGER PRIMARY KEY,
    legal_name   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invoices (
    id            INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
    reference     TEXT NOT NULL,
    amount_cents  INTEGER NOT NULL,
    currency      TEXT NOT NULL DEFAULT 'EUR',
    due_date      TEXT NOT NULL,             -- ISO-8601 date
    status        TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'paid'))
);

CREATE TABLE IF NOT EXISTS bank_lines (
    line_id         TEXT PRIMARY KEY,
    booking_date    TEXT NOT NULL,
    value_date      TEXT NOT NULL,
    remitter        TEXT,
    iban            TEXT,
    purpose         TEXT,
    amount_cents    INTEGER NOT NULL,
    currency        TEXT NOT NULL,
    statement_file  TEXT
);

CREATE TABLE IF NOT EXISTS match_results (
    line_id       TEXT NOT NULL REFERENCES bank_lines(line_id),
    invoice_id    INTEGER NOT NULL REFERENCES invoices(id),
    rule          TEXT NOT NULL,
    amount_cents  INTEGER NOT NULL,
    PRIMARY KEY (line_id, invoice_id)
);
RECON_EOF_07

mkdir -p "$(dirname recon/store/schema_v2.sql)"
cat > recon/store/schema_v2.sql <<'RECON_EOF_08'
-- schema version 2: stored normalised reference and the indexes the matcher and `lookup` rely on.
-- The reference_norm column itself is added by migrations.py (ALTER TABLE is not idempotent in SQLite).

CREATE INDEX IF NOT EXISTS ix_invoices_reference_norm   ON invoices(reference_norm);
CREATE INDEX IF NOT EXISTS ix_invoices_customer_status  ON invoices(customer_id, status);
CREATE INDEX IF NOT EXISTS ix_match_results_line        ON match_results(line_id);
RECON_EOF_08

mkdir -p "$(dirname recon/store/migrations.py)"
cat > recon/store/migrations.py <<'RECON_EOF_09'
"""Schema versioning. `apply_migrations` is run on every startup and is a no-op
for a database that is already at the current version.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from recon.matching.normalize import normalize_reference

log = logging.getLogger("recon.store")
_HERE = Path(__file__).parent


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _v2_reference_norm(conn: sqlite3.Connection) -> None:
    """Add invoices.reference_norm and fill it with the Python normaliser."""
    if "reference_norm" not in _column_names(conn, "invoices"):
        conn.execute("ALTER TABLE invoices ADD COLUMN reference_norm TEXT")
    backfill_reference_norm(conn)


def backfill_reference_norm(conn: sqlite3.Connection) -> int:
    """Fill reference_norm where missing, using the one and only normaliser.

    Runs as a single UPDATE with the Python function registered on the
    connection so the ledger and the matcher can never disagree on a value.
    """
    conn.create_function("recon_normalize", 1, normalize_reference, deterministic=True)
    cur = conn.execute(
        "UPDATE invoices SET reference_norm = recon_normalize(reference) "
        "WHERE reference_norm IS NULL OR reference_norm != recon_normalize(reference)"
    )
    return cur.rowcount


@dataclass(frozen=True)
class Migration:
    version: int
    sql_file: str | None = None
    python: Callable[[sqlite3.Connection], None] | None = None


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, sql_file="schema.sql"),
    Migration(2, python=_v2_reference_norm, sql_file="schema_v2.sql"),
)
CURRENT_VERSION = MIGRATIONS[-1].version


def current_version(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Bring the database to CURRENT_VERSION; returns the number of migrations applied."""
    applied = 0
    version = current_version(conn)
    for mig in MIGRATIONS:
        if mig.version <= version:
            continue
        log.info("migrating schema %d -> %d", version, mig.version)
        if mig.python is not None:
            mig.python(conn)
        if mig.sql_file:
            conn.executescript((_HERE / mig.sql_file).read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_version(version) VALUES (?)", (mig.version,))
        conn.commit()
        version = mig.version
        applied += 1
    return applied
RECON_EOF_09

mkdir -p "$(dirname recon/store/repository.py)"
cat > recon/store/repository.py <<'RECON_EOF_10'
"""SQLite access. One connection per Repository instance, one commit per run."""
from __future__ import annotations

import logging
import sqlite3
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

from recon.matching.normalize import normalize_reference
from recon.models import Customer, Invoice, MatchResult, StatementLine
from recon.store import migrations

log = logging.getLogger("recon.store")


def _row_to_invoice(row: sqlite3.Row) -> Invoice:
    return Invoice(
        id=int(row["id"]),
        customer_id=int(row["customer_id"]),
        reference=row["reference"],
        amount_cents=int(row["amount_cents"]),
        currency=row["currency"],
        due_date=date.fromisoformat(row["due_date"]),
        status=row["status"],
    )


class Repository:
    """Context manager owning a single SQLite connection for the whole run."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._conn: sqlite3.Connection | None = None

    # -- lifecycle ---------------------------------------------------------
    def open(self) -> "Repository":
        if self._conn is None:
            log.debug("sqlite3 connect %s", self.path)
            conn = sqlite3.connect(str(self.path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._conn = conn
        return self

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Repository":
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("repository is not open")
        return self._conn

    def commit(self) -> None:
        self.conn.commit()

    def migrate(self) -> int:
        return migrations.apply_migrations(self.conn)

    # -- reads -------------------------------------------------------------
    def load_invoices(self, status: str | None = None) -> list[Invoice]:
        """Bulk-load invoices (all statuses by default) ordered by (due_date, id)."""
        sql = "SELECT id, customer_id, reference, amount_cents, currency, due_date, status FROM invoices"
        params: tuple = ()
        if status is not None:
            sql += " WHERE status = ?"
            params = (status,)
        sql += " ORDER BY due_date, id"
        return [_row_to_invoice(r) for r in self.conn.execute(sql, params)]

    def get_invoice(self, invoice_id: int) -> Invoice | None:
        row = self.conn.execute(
            "SELECT id, customer_id, reference, amount_cents, currency, due_date, status FROM invoices WHERE id = ?",
            (invoice_id,),
        ).fetchone()
        return _row_to_invoice(row) if row else None

    def open_invoices_for_customer(self, customer_id: int) -> list[Invoice]:
        rows = self.conn.execute(
            "SELECT id, customer_id, reference, amount_cents, currency, due_date, status FROM invoices "
            "WHERE customer_id = ? AND status = 'open' ORDER BY due_date, id",
            (customer_id,),
        )
        return [_row_to_invoice(r) for r in rows]

    def invoices_by_reference(self, reference: str) -> list[Invoice]:
        """Sargable lookup on the stored normalised reference (any formatting variant)."""
        rows = self.conn.execute(
            "SELECT id, customer_id, reference, amount_cents, currency, due_date, status FROM invoices "
            "WHERE reference_norm = ? ORDER BY due_date, id",
            (normalize_reference(reference),),
        )
        return [_row_to_invoice(r) for r in rows]

    def count(self, table: str) -> int:
        return int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    # -- writes ------------------------------------------------------------
    def insert_customers(self, customers: Iterable[Customer]) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO customers(customer_id, legal_name) VALUES (?, ?)",
            ((c.customer_id, c.legal_name) for c in customers),
        )

    def insert_invoices(self, invoices: Iterable[Invoice]) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO invoices(id, customer_id, reference, reference_norm, amount_cents, currency, due_date, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (
                    inv.id,
                    inv.customer_id,
                    inv.reference,
                    normalize_reference(inv.reference),
                    inv.amount_cents,
                    inv.currency,
                    inv.due_date.isoformat(),
                    inv.status,
                )
                for inv in invoices
            ),
        )

    def insert_bank_lines(self, lines: Sequence[StatementLine], statement_file: str) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO bank_lines(line_id, booking_date, value_date, remitter, iban, purpose, "
            "amount_cents, currency, statement_file) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (
                    ln.line_id,
                    ln.booking_date.isoformat(),
                    ln.value_date.isoformat(),
                    ln.remitter,
                    ln.iban,
                    ln.purpose,
                    ln.amount_cents,
                    ln.currency,
                    statement_file,
                )
                for ln in lines
            ),
        )

    def record_matches(self, results: Iterable[MatchResult]) -> int:
        """Write match_results rows and flip invoice status in bulk; caller commits."""
        rows = [
            (res.line.line_id, inv.id, res.rule, res.line.amount_cents)
            for res in results
            if res.matched
            for inv in res.invoices
        ]
        self.conn.executemany(
            "INSERT OR REPLACE INTO match_results(line_id, invoice_id, rule, amount_cents) VALUES (?, ?, ?, ?)",
            rows,
        )
        self.conn.executemany(
            "UPDATE invoices SET status = 'paid' WHERE id = ?",
            ((r[1],) for r in rows),
        )
        return len(rows)
RECON_EOF_10

mkdir -p "$(dirname recon/pipeline/stages.py)"
cat > recon/pipeline/stages.py <<'RECON_EOF_11'
"""Per-line processing: candidates -> decision -> consumption, in spec order (section 6)."""
from __future__ import annotations

import logging
from typing import Sequence

from recon.config import DEFAULT_CONFIG, MatchConfig
from recon.customers.master import CustomerIndex
from recon.matching.candidates import InvoiceIndex, find_candidates
from recon.matching.decision import decide
from recon.matching.normalize import extract_reference_tokens
from recon.models import MatchResult, StatementLine
from recon.statements.parser import processing_order

log = logging.getLogger("recon.pipeline")


def process_line(
    line: StatementLine, index: InvoiceIndex, customers: CustomerIndex, config: MatchConfig
) -> MatchResult:
    tokens = extract_reference_tokens(line.purpose) if line.is_credit else []
    candidates = find_candidates(line, tokens, index, customers, config) if line.is_credit else []
    result = decide(line, tokens, candidates, index)
    if result.matched:
        index.consume(result.invoices)
    return result


def match_lines(
    lines: Sequence[StatementLine],
    index: InvoiceIndex,
    customers: CustomerIndex,
    config: MatchConfig = DEFAULT_CONFIG,
) -> list[MatchResult]:
    """Match every line in (booking_date, line_id) order; results come back in that order."""
    results: list[MatchResult] = []
    for n, line in enumerate(processing_order(lines), start=1):
        results.append(process_line(line, index, customers, config))
        if n % 2000 == 0:
            log.info("match: %d lines processed", n)
    return results
RECON_EOF_11

mkdir -p "$(dirname recon/pipeline/run.py)"
cat > recon/pipeline/run.py <<'RECON_EOF_12'
"""Pipeline orchestration: parse -> load -> match -> persist -> report.

Every stage logs `stage=<name> ... elapsed=<seconds>s` so the nightly log can
be read for timings.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from recon.config import DEFAULT_CONFIG, MatchConfig
from recon.customers.master import build_customer_index
from recon.matching.candidates import InvoiceIndex
from recon.pipeline.stages import match_lines
from recon.reporting.writer import Summary, write_reports
from recon.statements.parser import parse_statement
from recon.store.repository import Repository

log = logging.getLogger("recon.pipeline")


class _Stage:
    def __init__(self, name: str):
        self.name = name
        self.t0 = time.perf_counter()

    def done(self, **fields) -> None:
        extra = " ".join(f"{k}={v}" for k, v in fields.items())
        log.info("stage=%s %s elapsed=%.3fs", self.name, extra, time.perf_counter() - self.t0)


def run_pipeline(
    db_path: str | Path,
    statement_path: str | Path,
    customers_path: str | Path,
    out_dir: str | Path,
    config: MatchConfig = DEFAULT_CONFIG,
) -> Summary:
    statement_path = Path(statement_path)

    st = _Stage("parse")
    lines = parse_statement(statement_path)
    st.done(lines=len(lines))

    with Repository(db_path) as repo:
        st = _Stage("load")
        repo.migrate()
        customers = build_customer_index(customers_path)
        index = InvoiceIndex(repo.load_invoices())
        st.done(customers=len(customers), open_invoices=index.open_count)

        st = _Stage("match")
        results = match_lines(lines, index, customers, config)
        st.done(matched=sum(1 for r in results if r.matched))

        st = _Stage("persist")
        repo.insert_bank_lines(lines, statement_path.name)
        rows = repo.record_matches(results)
        repo.commit()
        st.done(match_rows=rows)

    st = _Stage("report")
    summary = write_reports(results, out_dir, statement_path.name)
    st.done(out=str(out_dir))
    return summary
RECON_EOF_12

mkdir -p "$(dirname scripts/load_ledger.py)"
cat > scripts/load_ledger.py <<'RECON_EOF_13'
"""Build (or rebuild) data/recon.db from the CSV exports of the ERP.

    python scripts/load_ledger.py --customers data/customers.csv --invoices data/invoices.csv --db data/recon.db

invoices.csv columns: id,customer_id,reference,amount_cents,currency,due_date,status
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recon.customers.master import load_customers  # noqa: E402
from recon.models import Invoice  # noqa: E402
from recon.store.repository import Repository  # noqa: E402


def read_invoices(path: Path) -> list[Invoice]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [
            Invoice(
                id=int(r["id"]),
                customer_id=int(r["customer_id"]),
                reference=r["reference"],
                amount_cents=int(r["amount_cents"]),
                currency=r["currency"],
                due_date=date.fromisoformat(r["due_date"]),
                status=r["status"],
            )
            for r in csv.DictReader(fh)
        ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--customers", required=True)
    ap.add_argument("--invoices", required=True)
    ap.add_argument("--db", required=True)
    args = ap.parse_args()

    db = Path(args.db)
    for suffix in ("", "-wal", "-shm", "-journal"):
        p = Path(str(db) + suffix)
        if p.exists():
            p.unlink()
    db.parent.mkdir(parents=True, exist_ok=True)

    customers = load_customers(args.customers)
    invoices = read_invoices(Path(args.invoices))
    with Repository(db) as repo:
        repo.migrate()
        repo.insert_customers(customers)
        repo.insert_invoices(invoices)
        repo.commit()
        print(f"{db}: {repo.count('customers')} customers, {repo.count('invoices')} invoices")
    return 0


if __name__ == "__main__":
    sys.exit(main())
RECON_EOF_13

mkdir -p "$(dirname CHANGES.md)"
cat > CHANGES.md <<'RECON_EOF_14'
# CHANGES — INCIDENT-2291 root causes and fixes

Full Nordwind August statement: killed at 2 h before → a few seconds now.
Matching results for rules A1, A2, B1, B2 are unchanged; rule B3 now follows
the specification for every customer.

## Root causes

1. **Ledger scanned per statement line with one SQL round-trip per invoice**
   (`matching/candidates.py`, `store/repository.py`). Every line iterated
   `all_invoice_ids()` and called `get_invoice(id)` for each of the ~39,500
   invoices — ~470 million queries for the statement, each on its own
   `sqlite3.connect`. Replaced by `InvoiceIndex`: the ledger is bulk-loaded
   once and indexed by normalised reference, customer (oldest first) and
   amount; consumed invoices are tracked in the index.

2. **Full Levenshtein against every invoice** (`matching/fuzzy.py`). Rule A2
   requires the amount to agree, so only invoices with the line's amount
   (±tolerance) are compared, using a banded, early-exit edit distance
   (`bounded_distance`) instead of the full matrix.

3. **Per-call connections, per-row commits, non-sargable reference lookup**
   (`store/repository.py`, `store/schema.sql`, `store/migrations.py`). The
   repository now holds one connection per run (WAL, `synchronous=NORMAL`),
   loads invoices in bulk and writes `bank_lines` / `match_results` / status
   updates with `executemany` and a single commit. Schema v2 adds
   `invoices.reference_norm` (backfilled by the Python normaliser registered
   as an SQLite function, so ledger and matcher can never disagree) plus
   indexes on `invoices(reference_norm)`, `invoices(customer_id, status)` and
   `match_results(line_id)`. `lookup` uses the indexed column and now finds
   references in any formatting variant; the old `lower(replace(...))`
   mirror ignored slashes, dots and leading zeros.

4. **Customer master re-read from CSV for every line** (`customers/master.py`,
   `pipeline/stages.py`). `identify_by_iban` / `identify_by_name` reloaded and
   re-indexed 3,000 customers per call (twice per line). Replaced by
   `CustomerIndex`, built once per run.

5. **Rule B3 implemented as a subset search with a 12-invoice cap**
   (`matching/batch.py`, `config.py`). The spec defines B3 over *contiguous*
   runs of the customer's available invoices in (due_date, id) order, 2–40
   invoices, within 60 days, earliest start wins. `find_batch` is now a
   prefix-sum scan over runs; `BATCH_SUBSET_CAP` is gone and the 17
   large-customer batch payments match.

Also hoisted regex compilation / translation table in `matching/normalize.py`
and cached `normalize_reference`.

## Migration note

`run` and `migrate` upgrade an existing ledger to schema v2 on startup
(idempotent). `scripts/load_ledger.py` populates `reference_norm` for fresh
imports.
RECON_EOF_14

find /app -name __pycache__ -type d -prune -exec rm -rf {} +
python -m pytest tests_unit -q -p no:cacheprovider
echo "INCIDENT-2291 fix applied"
