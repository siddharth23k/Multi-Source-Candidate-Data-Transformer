"""Date normalization to YYYY-MM (months) and YYYY (years)."""

from __future__ import annotations

import re
from typing import Optional

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_PRESENT = {"present", "current", "now", "till date", "to date"}


def normalize_month(value: Optional[str]) -> Optional[str]:
    """Accept 'Jan 2020', '01/2020', '2020-01', 'January 2020' -> '2020-01'.
    Accept 'Present' -> 'present'. Otherwise None."""
    if not value:
        return None
    v = value.strip().lower()
    if v in _PRESENT:
        return "present"

    # 2020-01 or 2020/01
    m = re.fullmatch(r"(\d{4})[-/](\d{1,2})", v)
    if m:
        return _fmt(int(m.group(1)), int(m.group(2)))

    # 01/2020 or 1-2020
    m = re.fullmatch(r"(\d{1,2})[-/](\d{4})", v)
    if m:
        return _fmt(int(m.group(2)), int(m.group(1)))

    # Month name + year: "jan 2020", "january, 2020"
    m = re.fullmatch(r"([a-z]+)\.?,?\s+(\d{4})", v)
    if m and m.group(1) in _MONTHS:
        return _fmt(int(m.group(2)), _MONTHS[m.group(1)])

    # A bare year is not valid for a YYYY-MM field, so we don't guess a month here;
    # year-only values are handled separately by normalize_year().
    return None


def normalize_year(value: Optional[str]) -> Optional[int]:
    """Extract a 4-digit year (1900-2099)."""
    if not value:
        return None
    m = re.search(r"(19|20)\d{2}", str(value))
    return int(m.group(0)) if m else None


def _fmt(year: int, month: int) -> Optional[str]:
    if not (1 <= month <= 12) or not (1900 <= year <= 2099):
        return None
    return f"{year:04d}-{month:02d}"
