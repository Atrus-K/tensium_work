#!/usr/bin/env bash
# Reference fix for LND-4127: bring pyledger to byte parity with LNACCR01.
#
# Root causes fixed (all in the port's COBOL-semantics layer, no per-account logic):
#   numeric.py   Decimal arithmetic; ROUNDED = half away from zero, unrounded store = truncate
#   accrual.py   two-step COMPUTE: daily rate truncated to PIC 9V9(9) before the multiply
#   copybook.py  zoned-decimal overpunch sign decoded on input and encoded on output
#   dates.py     2000-CENTURY-WINDOW (YY > 49 -> 19YY); 30/360 with both D1 and D2 clamps
#   fees.py      exclusive days-late (no +1), strict grace comparison, LM-WAIVE-FLAG honoured
#   status.py    EVALUATE TRUE ladder (> 90 W, > 60 X, > 30 D, > grace L, else C)
#   layouts.py   LNMAST copybook v3: LM-WAIVE-FLAG carved out of the FILLER at column 86
#   models.py    Account carries the waive flag
#   batch.py     carry the waive flag from the master record into the account model
set -euo pipefail
cd /app

cat > pyledger/numeric.py <<'PYEOF'
"""COBOL numeric semantics for the calculators.

LNACCR01 is compiled with ARITH(EXTEND): the intermediate result of a COMPUTE is
exact and only the store into the receiving item loses precision.  Two kinds of
store exist:

* ``COMPUTE X ROUNDED = ...`` -- rounds half away from zero to X's scale;
* ``COMPUTE X = ...`` / ``MOVE`` -- truncates (toward zero) to X's scale.

Both then drop any high-order digits that do not fit the PICTURE.  All money and
rate arithmetic in the port is done with :class:`decimal.Decimal` so that these
rules can be applied exactly; never route a value through ``float``.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, localcontext

from .copybook import Pic, fit_to_pic, parse_pic

ZERO = Decimal("0")
CENT = Decimal("0.01")

# Enough precision for 13-digit money * 10-digit rate * 3-digit day counts.
_PRECISION = 40


def D(value) -> Decimal:
    """Coerce ints / numeric strings / Decimals to Decimal without going through float."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        raise TypeError("float values are not allowed in COBOL arithmetic; pass str or Decimal")
    return Decimal(value)


def rounded(value: Decimal, scale: int) -> Decimal:
    """COMPUTE ... ROUNDED: half away from zero at *scale* decimals."""
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        return D(value).quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_UP)


def truncate(value: Decimal, scale: int) -> Decimal:
    """Unrounded COMPUTE / MOVE: drop low-order digits beyond *scale* (toward zero)."""
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        return D(value).quantize(Decimal(1).scaleb(-scale), rounding=ROUND_DOWN)


def fit_pic(value: Decimal, pic: str | Pic, rounded_store: bool = False) -> Decimal:
    """Store *value* into an item declared with PICTURE *pic* (e.g. ``"S9(9)V99"``)."""
    p = pic if isinstance(pic, Pic) else parse_pic(pic)
    v = rounded(D(value), p.scale) if rounded_store else D(value)
    return fit_to_pic(v, p)


def multiply(*factors: Decimal) -> Decimal:
    """Exact product of Decimal factors (the intermediate result of a COMPUTE)."""
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        result = Decimal(1)
        for f in factors:
            result *= D(f)
        return result


def divide(numerator: Decimal, denominator: Decimal) -> Decimal:
    """Exact-enough quotient (40 significant digits) for a subsequent PIC store."""
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        return D(numerator) / D(denominator)
PYEOF

cat > pyledger/copybook.py <<'PYEOF'
"""PIC-clause parser and fixed-width record codec.

The legacy files are RECFM=FB datasets transferred with a per-field conversion map
(see docs/file-transfer-notes.md): DISPLAY fields arrive as ASCII text, COMP-3
fields arrive as raw packed-decimal bytes.  Signed DISPLAY fields carry the sign in
the zone of the last digit, which after EBCDIC->ASCII conversion appears as an
"overpunch" character:

    positive:  {  A  B  C  D  E  F  G  H  I     (digits 0..9)
    negative:  }  J  K  L  M  N  O  P  Q  R     (digits 0..9)

Numeric fields decode to :class:`decimal.Decimal`; alphanumeric fields decode to
``str`` with trailing blanks preserved.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Any

_PIC_RE = re.compile(
    r"^(?P<sign>S)?(?P<int>(?:9(?:\((\d+)\))?)+)?(?:V(?P<frac>(?:9(?:\((\d+)\))?)+))?$"
)
_ALPHA_RE = re.compile(r"^X(?:\((\d+)\))?$")

_POS_OVERPUNCH = "{ABCDEFGHI"
_NEG_OVERPUNCH = "}JKLMNOPQR"
_DECODE_OVERPUNCH: dict[str, tuple[int, int]] = {}
for _d in range(10):
    _DECODE_OVERPUNCH[_POS_OVERPUNCH[_d]] = (_d, 1)
    _DECODE_OVERPUNCH[_NEG_OVERPUNCH[_d]] = (_d, -1)
    # some transfer profiles leave an unsigned zone on the last digit: treat as positive
    _DECODE_OVERPUNCH[str(_d)] = (_d, 1)


def _count_nines(spec: str) -> int:
    total = 0
    for m in re.finditer(r"9(?:\((\d+)\))?", spec):
        total += int(m.group(1)) if m.group(1) else 1
    return total


@dataclass(frozen=True)
class Pic:
    """A parsed PICTURE clause."""

    kind: str  # "num" or "alnum"
    signed: bool
    digits: int  # total digits (num) or characters (alnum)
    scale: int  # digits after the assumed decimal point
    usage: str  # "DISPLAY" or "COMP-3"

    @property
    def length(self) -> int:
        if self.kind == "alnum":
            return self.digits
        if self.usage == "COMP-3":
            return (self.digits + 2) // 2  # digits + sign nibble, rounded up to whole bytes
        return self.digits

    @property
    def integer_digits(self) -> int:
        return self.digits - self.scale


def parse_pic(text: str, usage: str = "DISPLAY") -> Pic:
    spec = text.replace(" ", "").upper()
    m = _ALPHA_RE.match(spec)
    if m:
        return Pic("alnum", False, int(m.group(1)) if m.group(1) else 1, 0, "DISPLAY")
    m = _PIC_RE.match(spec)
    if not m or (m.group("int") is None and m.group("frac") is None):
        raise ValueError(f"unsupported PICTURE clause: {text!r}")
    int_digits = _count_nines(m.group("int") or "")
    frac_digits = _count_nines(m.group("frac") or "")
    return Pic("num", m.group("sign") == "S", int_digits + frac_digits, frac_digits, usage.upper())


# ----------------------------------------------------------------- numeric moves

def fit_to_pic(value: Decimal, pic: Pic) -> Decimal:
    """Store *value* into a numeric PIC the way a COBOL MOVE does.

    Excess low-order digits are truncated (never rounded); excess high-order digits
    are dropped; an unsigned item receives the absolute value.
    """
    q = Decimal(1).scaleb(-pic.scale)
    v = value.quantize(q, rounding=ROUND_DOWN)
    limit = Decimal(10) ** pic.integer_digits
    negative = v < 0
    v = abs(v)
    if v >= limit:
        v = v % limit
    if negative and pic.signed:
        v = -v
    return v


def _digits_of(value: Decimal, pic: Pic) -> str:
    v = fit_to_pic(value, pic)
    text = f"{abs(v):.{pic.scale}f}".replace(".", "")
    return text.rjust(pic.digits, "0")


# ----------------------------------------------------------------- DISPLAY numeric

def decode_display(raw: bytes, pic: Pic) -> Decimal:
    text = raw.decode("ascii")
    if not pic.signed:
        if not text.isdigit():
            raise ValueError(f"non-numeric DISPLAY field {text!r}")
        return _place_point(text, pic.scale)
    body, last = text[:-1], text[-1]
    if not body.isdigit() or last not in _DECODE_OVERPUNCH:
        raise ValueError(f"bad zoned decimal field {text!r}")
    digit, sign = _DECODE_OVERPUNCH[last]
    return sign * _place_point(body + str(digit), pic.scale)


def encode_display(value: Decimal, pic: Pic) -> bytes:
    fitted = fit_to_pic(value, pic)
    digits = _digits_of(fitted, pic)
    if not pic.signed:
        return digits.encode("ascii")
    table = _NEG_OVERPUNCH if fitted < 0 else _POS_OVERPUNCH
    return (digits[:-1] + table[int(digits[-1])]).encode("ascii")


def _place_point(digits: str, scale: int) -> Decimal:
    if scale == 0:
        return Decimal(digits)
    return Decimal(digits[:-scale] + "." + digits[-scale:]) if len(digits) > scale \
        else Decimal("0." + digits.rjust(scale, "0"))


# ----------------------------------------------------------------- COMP-3 numeric

def decode_comp3(raw: bytes, pic: Pic) -> Decimal:
    nibbles: list[int] = []
    for b in raw:
        nibbles.append(b >> 4)
        nibbles.append(b & 0x0F)
    sign_nibble = nibbles[-1]
    digit_nibbles = nibbles[:-1][-pic.digits:]
    if any(n > 9 for n in digit_nibbles):
        raise ValueError(f"bad packed decimal field {raw.hex()}")
    magnitude = _place_point("".join(str(n) for n in digit_nibbles), pic.scale)
    if sign_nibble == 0x0D:
        return -magnitude
    if sign_nibble in (0x0C, 0x0F):
        return magnitude
    raise ValueError(f"bad packed decimal sign nibble {sign_nibble:x}")


def encode_comp3(value: Decimal, pic: Pic) -> bytes:
    fitted = fit_to_pic(value, pic)
    digits = _digits_of(fitted, pic)
    nibbles = [int(c) for c in digits]
    nibbles.append(0x0D if fitted < 0 else (0x0C if pic.signed else 0x0F))
    if len(nibbles) % 2:
        nibbles.insert(0, 0)
    return bytes((nibbles[i] << 4) | nibbles[i + 1] for i in range(0, len(nibbles), 2))


# ----------------------------------------------------------------- field / layout

@dataclass(frozen=True)
class Field:
    name: str
    pic: Pic
    offset: int

    @property
    def length(self) -> int:
        return self.pic.length

    @property
    def end(self) -> int:
        return self.offset + self.length

    def slice(self, record: bytes) -> bytes:
        return record[self.offset:self.end]

    def decode(self, record: bytes) -> Any:
        raw = self.slice(record)
        if self.pic.kind == "alnum":
            return raw.decode("ascii")
        if self.pic.usage == "COMP-3":
            return decode_comp3(raw, self.pic)
        return decode_display(raw, self.pic)

    def encode(self, value: Any) -> bytes:
        if self.pic.kind == "alnum":
            text = "" if value is None else str(value)
            return text.ljust(self.length)[: self.length].encode("ascii")
        dec = value if isinstance(value, Decimal) else Decimal(str(value))
        if self.pic.usage == "COMP-3":
            return encode_comp3(dec, self.pic)
        return encode_display(dec, self.pic)


class Layout:
    """An ordered set of fields describing one fixed-width record type."""

    def __init__(self, name: str, fields: list[tuple[str, str] | tuple[str, str, str]], terminator: bytes = b""):
        self.name = name
        self.terminator = terminator
        self.fields: list[Field] = []
        offset = 0
        for spec in fields:
            fname, pic_text = spec[0], spec[1]
            usage = spec[2] if len(spec) > 2 else "DISPLAY"
            pic = parse_pic(pic_text, usage)
            self.fields.append(Field(fname, pic, offset))
            offset += pic.length
        self.record_length = offset
        self._by_name = {f.name: f for f in self.fields}

    def __getitem__(self, name: str) -> Field:
        return self._by_name[name]

    def names(self) -> list[str]:
        return [f.name for f in self.fields]

    def decode(self, record: bytes) -> dict[str, Any]:
        if len(record) != self.record_length:
            raise ValueError(f"{self.name}: expected {self.record_length} bytes, got {len(record)}")
        return {f.name: f.decode(record) for f in self.fields}

    def encode(self, values: dict[str, Any]) -> bytes:
        out = bytearray()
        for f in self.fields:
            out += f.encode(values.get(f.name, "" if f.pic.kind == "alnum" else Decimal(0)))
        assert len(out) == self.record_length
        return bytes(out) + self.terminator

    def read_records(self, data: bytes) -> list[bytes]:
        """Split a dataset into raw records (stripping the per-record terminator if any)."""
        step = self.record_length + len(self.terminator)
        if len(data) % step:
            raise ValueError(f"{self.name}: dataset length {len(data)} is not a multiple of {step}")
        records = []
        for i in range(0, len(data), step):
            chunk = data[i:i + step]
            if self.terminator and not chunk.endswith(self.terminator):
                raise ValueError(f"{self.name}: record {i // step + 1} lacks terminator")
            records.append(chunk[: self.record_length])
        return records
PYEOF

cat > pyledger/layouts.py <<'PYEOF'
"""Record layouts mirroring the LNACCR01 copybooks (legacy/copybooks/*.cpy).

Field order and PICTURE clauses must match the copybooks exactly: offsets are derived
from them.  Terminators reflect how the datasets arrive from the MFT job
(docs/file-transfer-notes.md): LNMAST carries packed fields and is transferred as
raw 120-byte blocks; the all-DISPLAY files get a LF after every record.
"""
from __future__ import annotations

from .copybook import Layout

# LNMAST.cpy -- loan master, copybook v3 (2019-06).  120 bytes, no terminator.
LNMAST = Layout(
    "LNMAST",
    [
        ("LM-ACCT-NO", "9(10)"),
        ("LM-CUST-NAME", "X(30)"),
        ("LM-PRODUCT-CD", "X"),
        ("LM-STATUS", "X"),
        ("LM-ORIG-DATE", "9(6)"),
        ("LM-DUE-DATE", "9(6)"),
        ("LM-LAST-ACCR-DATE", "9(6)"),
        ("LM-PRIN-BAL", "S9(11)V99"),
        ("LM-PMT-DUE-AMT", "9(9)V99", "COMP-3"),
        ("LM-GRACE-DAYS", "99"),
        ("LM-BRANCH-CD", "X(4)"),
        ("LM-WAIVE-FLAG", "X"),
        ("FILLER-1", "X(3)"),
        ("LM-OFFICER-ID", "X(6)"),
        ("LM-LAST-PMT-DATE", "9(6)"),
        ("FILLER-2", "X(19)"),
    ],
)

# LNTRAN.cpy -- payment / reversal transactions.  40 bytes + LF.
LNTRAN = Layout(
    "LNTRAN",
    [
        ("TR-ACCT-NO", "9(10)"),
        ("TR-POST-DATE", "9(6)"),
        ("TR-SEQ-NO", "9(4)"),
        ("TR-TYPE", "X"),
        ("TR-AMOUNT", "S9(9)V99"),
        ("TR-VOID-FLAG", "X"),
        ("TR-CHANNEL", "X(3)"),
        ("FILLER", "X(4)"),
    ],
    terminator=b"\n",
)

# RATETBL.cpy -- header record then OCCURS DEPENDING ON tier rows.  40 bytes + LF.
RATETBL_HEADER = Layout(
    "RATETBL-HDR",
    [
        ("RH-REC-TYPE", "X"),
        ("RH-TIER-COUNT", "99"),
        ("RH-DESCRIPTION", "X(37)"),
    ],
    terminator=b"\n",
)

RATETBL_TIER = Layout(
    "RATETBL-TIER",
    [
        ("RT-REC-TYPE", "X"),
        ("RT-UPPER-BAL", "9(11)V99"),
        ("RT-ANNUAL-RATE", "9V9(5)"),
        ("RT-LATE-PCT", "9V9(4)"),
        ("RT-FEE-MIN", "9(5)V99"),
        ("RT-FEE-MAX", "9(5)V99"),
        ("FILLER", "X"),
    ],
    terminator=b"\n",
)

# LNOUT.cpy -- accrual output.  80 bytes + LF.  Detail and trailer share the record
# area (REDEFINES); LO-REC-TYPE / LT-REC-TYPE at the same position tells them apart.
LNOUT_DETAIL = Layout(
    "LNOUT-DETAIL",
    [
        ("LO-ACCT-NO", "9(10)"),
        ("LO-PRODUCT-CD", "X"),
        ("LO-ASOF-DATE", "9(8)"),
        ("LO-BALANCE", "S9(11)V99"),
        ("LO-ACCRUED-INT", "S9(9)V99"),
        ("LO-LATE-FEE", "9(7)V99"),
        ("LO-DAYS-LATE", "9(3)"),
        ("LO-STATUS", "X"),
        ("LO-RATE-TIER", "9"),
        ("LO-DAILY-RATE", "9V9(9)"),
        ("LO-ACCR-DAYS", "9(3)"),
        ("LO-REC-TYPE", "X"),
        ("FILLER", "X(9)"),
    ],
    terminator=b"\n",
)

LNOUT_TRAILER = Layout(
    "LNOUT-TRAILER",
    [
        ("LT-REC-COUNT", "9(7)"),
        ("LT-HASH-TOTAL", "9(11)"),
        ("LT-TOT-ACCRUED", "S9(11)V99"),
        ("LT-TOT-FEES", "9(11)V99"),
        ("LT-TOT-BALANCE", "S9(13)V99"),
        ("FILLER-1", "X(11)"),
        ("LT-REC-TYPE", "X"),
        ("FILLER-2", "X(9)"),
    ],
    terminator=b"\n",
)

REC_TYPE_DETAIL = "D"
REC_TYPE_TRAILER = "T"
REC_TYPE_OFFSET = LNOUT_DETAIL["LO-REC-TYPE"].offset

LAYOUTS = {
    "LNMAST": LNMAST,
    "LNTRAN": LNTRAN,
    "RATETBL-HDR": RATETBL_HEADER,
    "RATETBL-TIER": RATETBL_TIER,
    "LNOUT-DETAIL": LNOUT_DETAIL,
    "LNOUT-TRAILER": LNOUT_TRAILER,
}
PYEOF

cat > pyledger/models.py <<'PYEOF'
"""Plain data holders shared by the batch stages."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class RateTier:
    index: int  # 1-based, as in the COBOL OCCURS table
    upper_balance: Decimal
    annual_rate: Decimal
    late_pct: Decimal
    fee_min: Decimal
    fee_max: Decimal


@dataclass
class Transaction:
    account: int
    post_date: date
    seq: int
    tran_type: str  # 'P' payment, 'R' reversal
    amount: Decimal
    voided: bool
    channel: str


@dataclass
class Account:
    account: int
    name: str
    product: str
    status: str
    orig_date: date
    due_date: date
    last_accrual_date: date
    principal: Decimal
    payment_due: Decimal
    grace_days: int
    branch: str
    officer: str
    waive_late_fee: bool  # LM-WAIVE-FLAG = 'Y' (LNMAST copybook v3)

    @property
    def is_closed(self) -> bool:
        return self.status == "Z"


@dataclass
class AccountResult:
    account: Account
    new_balance: Decimal
    paid_amount: Decimal
    tier: RateTier
    daily_rate: Decimal
    accrual_days: int
    accrued_interest: Decimal
    days_late: int
    late_fee: Decimal
    status_letter: str


@dataclass
class BatchTotals:
    record_count: int = 0
    hash_total: int = 0
    total_accrued: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    total_balance: Decimal = Decimal("0")
    skipped_closed: int = 0
    results: list[AccountResult] = field(default_factory=list)
PYEOF

cat > pyledger/dates.py <<'PYEOF'
"""Date handling mirroring the LNACCR01 date paragraphs.

* YYMMDD fields use the program's century window (2000-CENTURY-WINDOW):
  a two-digit year above 49 belongs to the 1900s, otherwise to the 2000s.
* Day differences use FUNCTION INTEGER-OF-DATE arithmetic (exclusive: the
  difference between a date and the following day is 1).
* Mortgage products accrue on a 30/360 (US) basis (2300-DAYS-360); other products
  on actual days (2200-DAYS-ACTUAL).
* Due dates falling on a weekend or bank holiday roll forward to the next
  business day (2400-ROLL-BUSINESS-DAY).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

CENTURY_PIVOT = 49  # YY > 49 -> 19YY, else 20YY


def from_yymmdd(value: Decimal | int | str) -> date:
    text = f"{int(value):06d}"
    yy, mm, dd = int(text[0:2]), int(text[2:4]), int(text[4:6])
    century = 1900 if yy > CENTURY_PIVOT else 2000
    return date(century + yy, mm, dd)


def parse_asof(text: str) -> date:
    """Accept YYYY-MM-DD (CLI) or YYYYMMDD (JCL PARM style)."""
    digits = text.replace("-", "")
    if len(digits) != 8 or not digits.isdigit():
        raise ValueError(f"as-of date must be YYYY-MM-DD, got {text!r}")
    return date(int(digits[0:4]), int(digits[4:6]), int(digits[6:8]))


def to_yyyymmdd(d: date) -> int:
    return d.year * 10000 + d.month * 100 + d.day


_EPOCH = date(1600, 12, 31)  # INTEGER-OF-DATE(1601-01-01) = 1


def integer_of_date(d: date) -> int:
    return (d - _EPOCH).days


def days_between(start: date, end: date) -> int:
    """INTEGER-OF-DATE(end) - INTEGER-OF-DATE(start); negative if end precedes start."""
    return integer_of_date(end) - integer_of_date(start)


def days_360(start: date, end: date) -> int:
    """30/360 US day count with both end-of-month clamps."""
    d1, d2 = start.day, end.day
    if d1 == 31:
        d1 = 30
    if d2 == 31 and d1 >= 30:
        d2 = 30
    return 360 * (end.year - start.year) + 30 * (end.month - start.month) + (d2 - d1)


class BusinessCalendar:
    """Weekend + holiday calendar loaded from HOLIDAYS.dat (YYYYMMDD DESCRIPTION lines)."""

    def __init__(self, holidays: set[date]):
        self.holidays = frozenset(holidays)

    @classmethod
    def load(cls, path: str | Path) -> "BusinessCalendar":
        holidays: set[date] = set()
        with open(path, "r", encoding="ascii") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line.strip() or line.startswith("*"):
                    continue
                token = line[:8]
                holidays.add(date(int(token[0:4]), int(token[4:6]), int(token[6:8])))
        return cls(holidays)

    def is_business_day(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self.holidays

    def roll_forward(self, d: date) -> date:
        while not self.is_business_day(d):
            d += timedelta(days=1)
        return d
PYEOF

cat > pyledger/accrual.py <<'PYEOF'
"""Interest accrual for the period (3300-ACCRUE-INTEREST).

The COBOL computes in two stores:

    COMPUTE WS-DAILY-RATE = RT-ANNUAL-RATE(WS-TIER-IX) / WS-BASIS
    COMPUTE WS-ACCRUED ROUNDED = WS-NEW-BAL * WS-DAILY-RATE * WS-ACCR-DAYS

WS-DAILY-RATE is PIC 9V9(9) and the first COMPUTE is not ROUNDED, so the daily rate
is truncated to nine decimals before it is multiplied.  WS-ACCRUED is PIC S9(9)V99
and is ROUNDED (half away from zero).  Interest accrues only on a positive balance.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from .dates import days_360, days_between
from .models import RateTier
from .numeric import ZERO, divide, fit_pic, multiply, truncate

BASIS_360 = Decimal(360)
BASIS_365 = Decimal(365)
PRODUCT_MORTGAGE = "M"

DAILY_RATE_PIC = "9V9(9)"
ACCRUED_PIC = "S9(9)V99"
ACCR_DAYS_PIC = "S9(5)"


def basis_for(product: str) -> Decimal:
    return BASIS_360 if product == PRODUCT_MORTGAGE else BASIS_365


def accrual_days(product: str, last_accrual: date, asof: date) -> int:
    if product == PRODUCT_MORTGAGE:
        days = days_360(last_accrual, asof)
    else:
        days = days_between(last_accrual, asof)
    return int(fit_pic(Decimal(days), ACCR_DAYS_PIC))


def daily_rate(tier: RateTier, product: str) -> Decimal:
    """WS-DAILY-RATE: annual rate / basis, truncated to the PIC 9V9(9) scale."""
    return fit_pic(divide(tier.annual_rate, basis_for(product)), DAILY_RATE_PIC)


def accrued_interest(balance: Decimal, rate_per_day: Decimal, days: int) -> Decimal:
    """WS-ACCRUED ROUNDED = balance * daily rate * days, or zero when the balance is not positive."""
    if balance <= ZERO:
        return ZERO
    product = multiply(balance, rate_per_day, Decimal(days))
    return fit_pic(product, ACCRUED_PIC, rounded_store=True)


def accrue(balance: Decimal, tier: RateTier, product: str, last_accrual: date, asof: date):
    """Return (daily_rate, accrual_days, accrued_interest) for one account."""
    days = accrual_days(product, last_accrual, asof)
    rate = daily_rate(tier, product)
    interest = accrued_interest(balance, rate, days)
    return rate, days, interest


__all__ = ["accrue", "accrual_days", "accrued_interest", "basis_for", "daily_rate", "truncate"]
PYEOF

cat > pyledger/fees.py <<'PYEOF'
"""Days-late determination and late-fee assessment (3400-DAYS-LATE / 3500-ASSESS-LATE-FEE)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from .dates import BusinessCalendar, days_between
from .models import Account, RateTier
from .numeric import ZERO, fit_pic, multiply

LATE_FEE_PIC = "9(7)V99"
NEW_ACCOUNT_WINDOW_DAYS = 90  # no late fee while the account is 90 days old or younger


def days_late(account: Account, paid: Decimal, asof: date, calendar: BusinessCalendar) -> int:
    """Whole days from the rolled due date to the as-of date; zero when paid in full or not yet due.

    COMPUTE WS-DAYS-LATE = INTEGER-OF-DATE(as-of) - INTEGER-OF-DATE(rolled due date)
    """
    rolled_due = calendar.roll_forward(account.due_date)
    late = days_between(rolled_due, asof)
    if late < 0:
        late = 0
    if paid >= account.payment_due:
        late = 0
    return late


def is_new_account(account: Account, asof: date) -> bool:
    return days_between(account.orig_date, asof) <= NEW_ACCOUNT_WINDOW_DAYS


def late_fee(account: Account, tier: RateTier, late: int, asof: date) -> Decimal:
    """Tier percentage of the payment due, ROUNDED, then floored/capped by the tier fee bounds.

    The fee is assessed only when the account is past its grace period
    (days late strictly greater than LM-GRACE-DAYS), not flagged for waiver, and
    older than the new-account window.
    """
    if late <= account.grace_days:
        return ZERO
    if account.waive_late_fee:
        return ZERO
    if is_new_account(account, asof):
        return ZERO
    fee = fit_pic(multiply(account.payment_due, tier.late_pct), LATE_FEE_PIC, rounded_store=True)
    if fee < tier.fee_min:
        fee = tier.fee_min
    if fee > tier.fee_max:
        fee = tier.fee_max
    return fee
PYEOF

cat > pyledger/status.py <<'PYEOF'
"""Delinquency status letter (3600-SET-STATUS).

    EVALUATE TRUE
        WHEN WS-DAYS-LATE > 90              MOVE 'W' TO LO-STATUS   (write-off referral)
        WHEN WS-DAYS-LATE > 60              MOVE 'X' TO LO-STATUS   (severely delinquent)
        WHEN WS-DAYS-LATE > 30              MOVE 'D' TO LO-STATUS   (delinquent)
        WHEN WS-DAYS-LATE > LM-GRACE-DAYS   MOVE 'L' TO LO-STATUS   (late, past grace)
        WHEN OTHER                          MOVE 'C' TO LO-STATUS   (current)
    END-EVALUATE

EVALUATE takes the first WHEN that is true, so the thresholds are tested from the
most severe downwards and every comparison is strict.
"""
from __future__ import annotations

STATUS_CURRENT = "C"
STATUS_LATE = "L"
STATUS_DELINQUENT = "D"
STATUS_SEVERE = "X"
STATUS_WRITEOFF = "W"

LADDER = (
    (90, STATUS_WRITEOFF),
    (60, STATUS_SEVERE),
    (30, STATUS_DELINQUENT),
)


def status_letter(days_late: int, grace_days: int) -> str:
    for threshold, letter in LADDER:
        if days_late > threshold:
            return letter
    if days_late > grace_days:
        return STATUS_LATE
    return STATUS_CURRENT
PYEOF

cat > pyledger/batch.py <<'PYEOF'
"""Batch orchestration: the Python counterpart of LNACCR01's PROCEDURE DIVISION.

    read LNMAST -> apply LNTRAN -> find tier -> accrue -> days late -> late fee
    -> status -> write LNOUT detail; closed accounts are skipped before any of
    it; the trailer carries count / hash / money totals over written records.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .accrual import accrue
from .dates import BusinessCalendar, from_yymmdd
from .fees import days_late, late_fee
from .layouts import LNMAST
from .models import Account, AccountResult, BatchTotals
from .numeric import ZERO, fit_pic
from .rates import RateTable
from .status import status_letter
from .transactions import apply_payments, group_by_account, load_transactions, paid_in_period
from .writer import LnoutWriter

log = logging.getLogger("pyledger.batch")

HASH_MODULUS = 10 ** 11  # LT-HASH-TOTAL PIC 9(11)
TOT_ACCRUED_PIC = "S9(11)V99"
TOT_FEES_PIC = "9(11)V99"
TOT_BALANCE_PIC = "S9(13)V99"


@dataclass
class BatchInputs:
    master: Path
    transactions: Path
    rates: Path
    holidays: Path
    asof: date
    output: Path


def load_master(path: str | Path) -> list[Account]:
    data = Path(path).read_bytes()
    accounts: list[Account] = []
    for raw in LNMAST.read_records(data):
        rec = LNMAST.decode(raw)
        accounts.append(
            Account(
                account=int(rec["LM-ACCT-NO"]),
                name=rec["LM-CUST-NAME"].rstrip(),
                product=rec["LM-PRODUCT-CD"],
                status=rec["LM-STATUS"],
                orig_date=from_yymmdd(rec["LM-ORIG-DATE"]),
                due_date=from_yymmdd(rec["LM-DUE-DATE"]),
                last_accrual_date=from_yymmdd(rec["LM-LAST-ACCR-DATE"]),
                principal=rec["LM-PRIN-BAL"],
                payment_due=rec["LM-PMT-DUE-AMT"],
                grace_days=int(rec["LM-GRACE-DAYS"]),
                branch=rec["LM-BRANCH-CD"],
                waive_late_fee=rec["LM-WAIVE-FLAG"] == "Y",
                officer=rec["LM-OFFICER-ID"].rstrip(),
            )
        )
    return accounts


def process_account(account: Account, paid, rates: RateTable, calendar: BusinessCalendar, asof: date) -> AccountResult:
    new_balance = apply_payments(account.principal, paid)
    tier = rates.find_tier(new_balance)
    rate, days, interest = accrue(new_balance, tier, account.product, account.last_accrual_date, asof)
    late = days_late(account, paid, asof, calendar)
    fee = late_fee(account, tier, late, asof)
    letter = status_letter(late, account.grace_days)
    return AccountResult(
        account=account,
        new_balance=new_balance,
        paid_amount=paid,
        tier=tier,
        daily_rate=rate,
        accrual_days=days,
        accrued_interest=interest,
        days_late=late,
        late_fee=fee,
        status_letter=letter,
    )


def accumulate(totals: BatchTotals, result: AccountResult) -> None:
    totals.record_count += 1
    totals.hash_total = (totals.hash_total + result.account.account) % HASH_MODULUS
    totals.total_accrued = fit_pic(totals.total_accrued + result.accrued_interest, TOT_ACCRUED_PIC)
    totals.total_fees = fit_pic(totals.total_fees + result.late_fee, TOT_FEES_PIC)
    totals.total_balance = fit_pic(totals.total_balance + result.new_balance, TOT_BALANCE_PIC)


def run_batch(inputs: BatchInputs) -> BatchTotals:
    calendar = BusinessCalendar.load(inputs.holidays)
    rates = RateTable.load(inputs.rates)
    transactions = group_by_account(load_transactions(inputs.transactions))
    accounts = load_master(inputs.master)
    log.info("LNACCR01 as-of %s: %d master records, %d tiers", inputs.asof, len(accounts), len(rates.tiers))

    totals = BatchTotals()
    with LnoutWriter(inputs.output) as out:
        for account in accounts:
            if account.is_closed:
                totals.skipped_closed += 1
                continue
            paid = paid_in_period(transactions.get(account.account, []))
            result = process_account(account, paid, rates, calendar, inputs.asof)
            out.write_detail(result, inputs.asof)
            accumulate(totals, result)
            totals.results.append(result)
        out.write_trailer(totals)
    log.info("wrote %d detail records (+ trailer) to %s; %d closed accounts skipped",
             totals.record_count, inputs.output, totals.skipped_closed)
    return totals


__all__ = ["BatchInputs", "BatchTotals", "load_master", "process_account", "run_batch", "ZERO"]
PYEOF


find /app/pyledger -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
python -m pyledger --version
echo "LND-4127 reference fix applied"
