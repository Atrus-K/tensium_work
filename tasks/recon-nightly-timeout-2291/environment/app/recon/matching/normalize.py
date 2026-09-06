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
