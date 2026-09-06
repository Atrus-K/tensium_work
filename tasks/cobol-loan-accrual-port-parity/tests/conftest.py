"""Shared helpers for the LNACCR01 parity suite.

Everything here is independent of the pyledger package: the tests drive the CLI
as a subprocess and slice its output with offsets taken straight from
legacy/copybooks/LNOUT.cpy.  Input fixtures for the mini-cases are encoded with a
tiny encoder of our own (zoned overpunch + COMP-3) derived from the copybooks.
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

APP_DIR = Path(os.environ.get("PYLEDGER_APP", os.getcwd())).resolve()
TESTS_DIR = Path(__file__).resolve().parent
FIXTURES = TESTS_DIR / "fixtures"

# ---------------------------------------------------------------- LNOUT layout (LNOUT.cpy)
# name -> (start offset 0-based, length)
DETAIL_FIELDS: dict[str, tuple[int, int]] = {
    "ACCT_NO": (0, 10),
    "PRODUCT_CD": (10, 1),
    "ASOF_DATE": (11, 8),
    "BALANCE": (19, 13),
    "ACCRUED_INT": (32, 11),
    "LATE_FEE": (43, 9),
    "DAYS_LATE": (52, 3),
    "STATUS": (55, 1),
    "RATE_TIER": (56, 1),
    "DAILY_RATE": (57, 10),
    "ACCR_DAYS": (67, 3),
    "REC_TYPE": (70, 1),
    "FILLER": (71, 9),
}
TRAILER_FIELDS: dict[str, tuple[int, int]] = {
    "REC_COUNT": (0, 7),
    "HASH_TOTAL": (7, 11),
    "TOT_ACCRUED": (18, 13),
    "TOT_FEES": (31, 13),
    "TOT_BALANCE": (44, 15),
    "FILLER_1": (59, 11),
    "REC_TYPE": (70, 1),
    "FILLER_2": (71, 9),
}
RECORD_LENGTH = 80

POS_OVERPUNCH = "{ABCDEFGHI"
NEG_OVERPUNCH = "}JKLMNOPQR"


def zoned_to_decimal(text: str, scale: int) -> Decimal:
    """Decode a signed zoned DISPLAY field (trailing overpunch) into a Decimal."""
    body, last = text[:-1], text[-1]
    if last in POS_OVERPUNCH:
        sign, digit = 1, POS_OVERPUNCH.index(last)
    elif last in NEG_OVERPUNCH:
        sign, digit = -1, NEG_OVERPUNCH.index(last)
    else:
        raise AssertionError(f"not an overpunched zoned field: {text!r}")
    assert body.isdigit(), text
    return sign * (Decimal(body + str(digit)) / (Decimal(10) ** scale))


def unsigned_to_decimal(text: str, scale: int) -> Decimal:
    assert text.isdigit(), f"not an unsigned numeric field: {text!r}"
    return Decimal(text) / (Decimal(10) ** scale)


def zoned(value: Decimal | str | int, digits: int, scale: int) -> str:
    """Encode a signed zoned DISPLAY field with trailing overpunch."""
    v = Decimal(str(value))
    text = f"{abs(v):.{scale}f}".replace(".", "").rjust(digits, "0")
    assert len(text) == digits, (value, digits, scale)
    table = NEG_OVERPUNCH if v < 0 else POS_OVERPUNCH
    return text[:-1] + table[int(text[-1])]


def unsigned(value: Decimal | str | int, digits: int, scale: int) -> str:
    v = Decimal(str(value))
    assert v >= 0
    text = f"{v:.{scale}f}".replace(".", "").rjust(digits, "0")
    assert len(text) == digits, (value, digits, scale)
    return text


def comp3(value: Decimal | str | int, digits: int, scale: int) -> bytes:
    """Encode an unsigned COMP-3 field (sign nibble F)."""
    v = Decimal(str(value))
    assert v >= 0
    text = f"{v:.{scale}f}".replace(".", "").rjust(digits, "0")
    nibbles = [int(c) for c in text] + [0xF]
    if len(nibbles) % 2:
        nibbles.insert(0, 0)
    return bytes((nibbles[i] << 4) | nibbles[i + 1] for i in range(0, len(nibbles), 2))


def yymmdd(d: date) -> str:
    return f"{d.year % 100:02d}{d.month:02d}{d.day:02d}"


# ---------------------------------------------------------------- output parsing

@dataclass
class LnoutFile:
    details: dict[str, str] = field(default_factory=dict)  # acct -> 80-byte record text
    order: list[str] = field(default_factory=list)
    trailer: str | None = None
    raw: bytes = b""

    def field(self, acct: str, name: str) -> str:
        start, length = DETAIL_FIELDS[name]
        return self.details[acct][start:start + length]

    def trailer_field(self, name: str) -> str:
        assert self.trailer is not None
        start, length = TRAILER_FIELDS[name]
        return self.trailer[start:start + length]


def parse_lnout(path: Path) -> LnoutFile:
    data = path.read_bytes()
    out = LnoutFile(raw=data)
    step = RECORD_LENGTH + 1
    assert len(data) % step == 0, f"{path}: {len(data)} bytes is not a whole number of 80-byte LF-terminated records"
    for i in range(0, len(data), step):
        rec = data[i:i + step]
        assert rec.endswith(b"\n"), f"{path}: record {i // step + 1} is not LF-terminated"
        text = rec[:RECORD_LENGTH].decode("ascii")
        rtype = text[70]
        if rtype == "T":
            assert out.trailer is None, "more than one trailer record"
            out.trailer = text
        else:
            assert rtype == "D", f"unknown record type {rtype!r} in record {i // step + 1}"
            acct = text[0:10]
            assert acct not in out.details, f"duplicate detail for {acct}"
            out.details[acct] = text
            out.order.append(acct)
    assert out.trailer is not None, f"{path}: no trailer record"
    return out


def field_diffs(expected: LnoutFile, actual: LnoutFile) -> list[str]:
    """Field-by-field differences (same format as the recon report) for actionable failures."""
    diffs: list[str] = []
    for acct in expected.order:
        if acct not in actual.details:
            diffs.append(f"{acct}  <missing in candidate>")
            continue
        for name in DETAIL_FIELDS:
            e, a = expected.field(acct, name), actual.field(acct, name)
            if e != a:
                diffs.append(f"{acct}  {name:<12} expected={e!r} actual={a!r}")
    for acct in actual.order:
        if acct not in expected.details:
            diffs.append(f"{acct}  <extra in candidate>")
    for name in TRAILER_FIELDS:
        e, a = expected.trailer_field(name), actual.trailer_field(name)
        if e != a:
            diffs.append(f"TRAILER     {name:<12} expected={e!r} actual={a!r}")
    if expected.order != actual.order:
        diffs.append("detail record order differs from the mainframe output")
    return diffs


# ---------------------------------------------------------------- CLI runner

def run_cli(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        [sys.executable, "-m", "pyledger", *args],
        cwd=APP_DIR,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if check:
        assert proc.returncode == 0, f"pyledger {' '.join(args)} failed ({proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    return proc


def run_batch(master: Path, trans: Path, rates: Path, holidays: Path, asof: str, out: Path) -> LnoutFile:
    run_cli(
        "run",
        "--master", str(master),
        "--trans", str(trans),
        "--rates", str(rates),
        "--holidays", str(holidays),
        "--asof", asof,
        "--out", str(out),
    )
    assert out.exists(), f"{out} was not written"
    return parse_lnout(out)


# ---------------------------------------------------------------- mini-batch builder

@dataclass
class MasterRow:
    acct: int
    product: str = "A"
    status: str = "A"
    orig: date = date(2015, 6, 1)
    due: date = date(2024, 4, 15)
    last_accr: date = date(2024, 2, 29)
    principal: str = "10000.00"
    payment_due: str = "250.00"
    grace: int = 10
    waive: str = " "
    name: str = "TEST ACCOUNT"


@dataclass
class TranRow:
    acct: int
    post: date
    seq: int
    ttype: str  # 'P' / 'R'
    amount: str
    void: str = " "


@dataclass
class Tier:
    upper: str
    rate: str
    pct: str
    fee_min: str
    fee_max: str


def master_record(m: MasterRow) -> bytes:
    rec = (
        f"{m.acct:010d}".encode()
        + m.name.ljust(30)[:30].encode()
        + m.product.encode()
        + m.status.encode()
        + yymmdd(m.orig).encode()
        + yymmdd(m.due).encode()
        + yymmdd(m.last_accr).encode()
        + zoned(m.principal, 13, 2).encode()
        + comp3(m.payment_due, 11, 2)
        + f"{m.grace:02d}".encode()
        + b"0101"
        + m.waive.encode()
        + b"   "
        + b"T00001"
        + b"240201"
        + b" " * 19
    )
    assert len(rec) == 120
    return rec


def tran_record(t: TranRow) -> str:
    rec = f"{t.acct:010d}{yymmdd(t.post)}{t.seq:04d}{t.ttype}{zoned(t.amount, 11, 2)}{t.void}ACH    "
    assert len(rec) == 40
    return rec


def rate_table(tiers: list[Tier]) -> str:
    lines = ["H" + f"{len(tiers):02d}" + "TEST RATE TIERS".ljust(37)]
    for t in tiers:
        line = "T" + unsigned(t.upper, 13, 2) + unsigned(t.rate, 6, 5) + unsigned(t.pct, 5, 4) \
            + unsigned(t.fee_min, 7, 2) + unsigned(t.fee_max, 7, 2) + " "
        assert len(line) == 40
        lines.append(line)
    return "\n".join(lines) + "\n"


US_HOLIDAYS_2024 = ["20231225", "20240101", "20240115", "20240219", "20240527", "20240704"]

SINGLE_TIER = [Tier("99999999999.99", "0.06125", "0.0400", "25.00", "150.00")]
MARCH_TIERS = [
    Tier("5000.00", "0.07250", "0.0500", "15.00", "50.00"),
    Tier("25000.00", "0.06750", "0.0450", "20.00", "75.00"),
    Tier("100000.00", "0.06125", "0.0400", "25.00", "150.00"),
    Tier("250000.00", "0.05625", "0.0350", "35.00", "250.00"),
    Tier("99999999999.99", "0.04875", "0.0300", "50.00", "500.00"),
]


class MiniBatch:
    """Writes a tiny LNMAST/LNTRAN/RATETBL/HOLIDAYS set into a temp dir and runs the CLI on it."""

    def __init__(self, tmp_path: Path):
        self.dir = tmp_path
        self.masters: list[MasterRow] = []
        self.trans: list[TranRow] = []
        self.tiers: list[Tier] = list(SINGLE_TIER)
        self.holidays: list[str] = list(US_HOLIDAYS_2024)

    def add(self, *rows: MasterRow) -> "MiniBatch":
        self.masters.extend(rows)
        return self

    def pay(self, *rows: TranRow) -> "MiniBatch":
        self.trans.extend(rows)
        return self

    def run(self, asof: str) -> LnoutFile:
        (self.dir / "LNMAST.dat").write_bytes(b"".join(master_record(m) for m in self.masters))
        (self.dir / "LNTRAN.dat").write_text("".join(tran_record(t) + "\n" for t in self.trans), encoding="ascii", newline="")
        (self.dir / "RATETBL.dat").write_text(rate_table(self.tiers), encoding="ascii", newline="")
        (self.dir / "HOLIDAYS.dat").write_text(
            "* TEST HOLIDAYS\n" + "".join(f"{h} HOLIDAY\n" for h in self.holidays), encoding="ascii", newline="")
        return run_batch(
            self.dir / "LNMAST.dat", self.dir / "LNTRAN.dat", self.dir / "RATETBL.dat",
            self.dir / "HOLIDAYS.dat", asof, self.dir / "LNOUT.dat",
        )


@pytest.fixture
def mini(tmp_path: Path) -> MiniBatch:
    return MiniBatch(tmp_path)


@pytest.fixture(scope="session")
def march_output(tmp_path_factory: pytest.TempPathFactory) -> LnoutFile:
    out = tmp_path_factory.mktemp("march") / "LNOUT_202403.dat"
    data = APP_DIR / "data"
    return run_batch(
        data / "LNMAST_202403.dat", data / "LNTRAN_202403.dat", data / "RATETBL_202403.dat",
        data / "HOLIDAYS.dat", "2024-03-31", out,
    )


@pytest.fixture(scope="session")
def march_expected() -> LnoutFile:
    return parse_lnout(APP_DIR / "data" / "MAINFRAME_LNOUT_202403.dat")


@pytest.fixture(scope="session")
def may_output(tmp_path_factory: pytest.TempPathFactory) -> LnoutFile:
    out = tmp_path_factory.mktemp("may") / "LNOUT_202405.dat"
    fx = FIXTURES / "batch_202405"
    return run_batch(
        fx / "LNMAST_202405.dat", fx / "LNTRAN_202405.dat", fx / "RATETBL_202405.dat",
        fx / "HOLIDAYS.dat", "2024-05-31", out,
    )


@pytest.fixture(scope="session")
def may_expected() -> LnoutFile:
    return parse_lnout(FIXTURES / "batch_202405" / "MAINFRAME_LNOUT_202405.dat")
