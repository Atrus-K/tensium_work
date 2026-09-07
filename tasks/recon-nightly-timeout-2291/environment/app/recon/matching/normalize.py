"""Text normalisation and reference-token extraction (matching_rules.md section 1)."""
from __future__ import annotations

import re

_UMLAUTS = (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("Ä", "AE"), ("Ö", "OE"), ("Ü", "UE"), ("ß", "ss"))


def normalize_reference(text: str) -> str:
    """Apply the four normalisation steps of section 1.1, in order."""
    for src, dst in _UMLAUTS:
        text = text.replace(src, dst)
    text = text.upper()
    text = re.sub(r"[0-9]+", lambda m: m.group(0).lstrip("0") or "0", text)
    return re.sub(r"[^A-Z0-9]", "", text)


def extract_reference_tokens(purpose: str) -> list[str]:
    """Distinct normalised reference tokens of a purpose text, in order of appearance."""
    # Section 1.2: 1-3 letters, optional separator, four digits, optional separator, 1-8 digits.
    pattern = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{1,3}[ \-/.]?[0-9]{4}[ \-/.]?[0-9]{1,8}(?![0-9])")
    tokens: list[str] = []
    for match in pattern.finditer(purpose):
        norm = normalize_reference(match.group(0))
        if norm not in tokens:
            tokens.append(norm)
    return tokens


def normalize_iban(iban: str) -> str:
    return "".join(iban.split()).upper()
