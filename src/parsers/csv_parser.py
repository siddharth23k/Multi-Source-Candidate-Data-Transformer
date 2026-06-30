"""Recruiter CSV export parser (structured source).

Expected-ish columns (case/space insensitive): name, email, phone,
current_company, title, location, skills, years_experience. mapping done loosely so a
slightly different header still works, and unknown columns ignored.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from typing import Optional

from ..models import Claim, SourceBlock

log = logging.getLogger("pipeline.csv")
SOURCE = "recruiter_csv"

# CSV cells are hand-entered structured data: high parser confidence.
CONF = 0.9

# Map normalized header -> canonical field handling.
_HEADER_ALIASES = {
    "name": "name", "full_name": "name", "candidate_name": "name",
    "email": "email", "email_address": "email", "e_mail": "email",
    "phone": "phone", "phone_number": "phone", "mobile": "phone",
    "current_company": "company", "company": "company", "employer": "company",
    "title": "title", "current_title": "title", "role": "title",
    "location": "location", "city": "location",
    "skills": "skills", "skill": "skills",
    "years_experience": "years", "yoe": "years", "experience_years": "years",
}


def _norm_header(h: str) -> str:
    return h.strip().lower().replace(" ", "_").replace("-", "_")


def parse(text: Optional[str], diag=None) -> list[SourceBlock]:
    """Parse raw CSV text into one SourceBlock per row. Returns [] on bad input."""
    if not text or not text.strip():
        if diag is not None:
            diag.warn("parse_csv", "empty_source", "CSV source was empty or missing")
        return []
    try:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return []
        field_map = {fn: _HEADER_ALIASES.get(_norm_header(fn)) for fn in reader.fieldnames}
        if not any(field_map.values()) and diag is not None:
            diag.warn("parse_csv", "no_known_columns",
                      "no recognised columns in CSV header", header=reader.fieldnames)
        blocks: list[SourceBlock] = []
        for i, row in enumerate(reader, start=2):  # row 1 = header
            try:
                block = _parse_row(row, field_map)
            except (ValueError, AttributeError) as e:
                if diag is not None:
                    diag.warn("parse_csv", "malformed_row", f"row {i} skipped: {e}", row=i)
                continue
            if block and block.claims:
                blocks.append(block)
            elif diag is not None:
                diag.info("parse_csv", "empty_row", f"row {i} produced no usable fields", row=i)
        return blocks
    except (csv.Error, ValueError) as e:
        log.warning("malformed CSV: %s", e)
        if diag is not None:
            diag.warn("parse_csv", "malformed_csv", f"CSV could not be parsed: {e}")
        return []


def _parse_row(row: dict, field_map: dict) -> Optional[SourceBlock]:
    claims: list[Claim] = []

    for col, canon in field_map.items():
        if canon is None:
            continue
        raw = (row.get(col) or "").strip()
        if not raw:
            continue

        if canon == "name":
            claims.append(Claim(field="full_name", value=raw, source=SOURCE,
                                method="csv_cell", confidence=CONF, raw=raw))
        elif canon == "email":
            for e in _split(raw):
                claims.append(Claim(field="emails", value=e, source=SOURCE,
                                    method="csv_cell", confidence=CONF, raw=e))
        elif canon == "phone":
            for p in _split(raw):
                claims.append(Claim(field="phones", value=p, source=SOURCE,
                                    method="csv_cell", confidence=CONF, raw=p))
        elif canon == "location":
            claims.append(Claim(field="location", value=raw, source=SOURCE,
                                method="csv_cell", confidence=CONF, raw=raw))
        elif canon == "company":
            # Current company -> a partial experience entry (title from the title column).
            claims.append(Claim(field="experience",
                                value={"company": raw, "title": _row_value(row, field_map, "title")},
                                source=SOURCE, method="csv_cell", confidence=CONF, raw=raw))
        elif canon == "skills":
            for s in _split(raw):
                claims.append(Claim(field="skills", value=s, source=SOURCE,
                                    method="csv_cell", confidence=CONF, raw=s))
        elif canon == "years":
            claims.append(Claim(field="years_experience", value=raw, source=SOURCE,
                                method="csv_cell", confidence=CONF, raw=raw))

    if not claims:
        return None
    return SourceBlock(source=SOURCE, claims=claims)


def _row_value(row: dict, field_map: dict, canon: str) -> Optional[str]:
    for col, c in field_map.items():
        if c == canon:
            v = (row.get(col) or "").strip()
            return v or None
    return None


def _split(raw: str) -> list[str]:
    """Split a multi-value cell on ; , | / and trim."""
    return [p.strip() for p in re.split(r"[;,|/]", raw) if p.strip()]
