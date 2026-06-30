"""Generic text normalizers: names, emails, company names."""

from __future__ import annotations

import re
from typing import Optional

_WS = re.compile(r"\s+")

# Common company suffixes stripped when comparing two company names so that
# "Google" and "Google LLC" are recognised as the same employer.
_COMPANY_SUFFIXES = re.compile(
    r"\b(inc|inc\.|llc|l\.l\.c\.|ltd|ltd\.|limited|corp|corp\.|corporation|"
    r"co|co\.|company|gmbh|plc|pvt|private)\b",
    re.IGNORECASE,
)


def clean_ws(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = _WS.sub(" ", value).strip()
    return value or None


def normalize_name(value: Optional[str]) -> Optional[str]:
    """Collapse whitespace and apply title case, but leave existing mixed-case
    tokens (e.g. 'McDonald', 'O'Brien') mostly alone by only title-casing
    all-lower or all-upper tokens."""
    value = clean_ws(value)
    if not value:
        return None
    out = []
    for tok in value.split(" "):
        if tok.islower() or tok.isupper():
            out.append(tok.capitalize())
        else:
            out.append(tok)
    return " ".join(out)


def normalize_email(value: Optional[str]) -> Optional[str]:
    """Lowercase + trim. Returns None if it does not look like an email."""
    value = clean_ws(value)
    if not value:
        return None
    value = value.lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        return None
    return value


def company_key(value: Optional[str]) -> str:
    """A comparison key for company names: lowercase, punctuation removed,
    legal suffixes stripped. NOT shown to users — only used for matching."""
    value = clean_ws(value) or ""
    value = value.lower()
    value = _COMPANY_SUFFIXES.sub("", value)
    value = re.sub(r"[^a-z0-9 ]", "", value)
    return _WS.sub(" ", value).strip()
