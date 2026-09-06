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
