"""Resume parser (unstructured source).

Resume prose has no schema, so layered heuristics are used and each claim is tagged with
method + confidence that reflects how reliable that heuristic is:
  - regex-matched contacts (email/phone)        -> high confidence
  - section-based extraction (skills/education)  -> medium
  - free-text guesses (name from first line)    -> lower
data never invented. Iif a section is absent then nothing emmitted from it.
"""

from __future__ import annotations

import re
from typing import Optional

from ..models import Claim, SourceBlock

SOURCE = "resume_pdf"

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(\+?\d[\d\s().\-]{7,}\d)")
_URL_RE = re.compile(r"(https?://[^\s]+|(?:www\.)?(?:linkedin\.com|github\.com)/[^\s]+)", re.I)

# Section headers recognised (line is mostly just the header word).
_SECTIONS = {
    "skills": ["skills", "technical skills", "core competencies", "technologies"],
    "experience": ["experience", "work experience", "professional experience", "employment"],
    "education": ["education", "academic background"],
    "summary": ["summary", "about", "profile", "objective"],
}

# A date range like "Jan 2020 - Present" or "2019 – 2021".
_DATE_RANGE = re.compile(
    r"((?:[A-Za-z]{3,9}\.?\s+)?\d{4})\s*[-–—to]+\s*((?:[A-Za-z]{3,9}\.?\s+)?\d{4}|present|current)",
    re.I,
)


def parse(text: Optional[str], diag=None) -> list[SourceBlock]:
    if not text or not text.strip():
        if diag is not None:
            diag.warn("parse_resume", "empty_source",
                      "resume text was empty (missing, corrupt, or image-only PDF)")
        return []
    lines = [ln.rstrip() for ln in text.splitlines()]
    nonempty = [ln for ln in lines if ln.strip()]
    claims: list[Claim] = []

    # Contacts (high confidence)
    for e in dict.fromkeys(_EMAIL_RE.findall(text)):   # dedupe, keep order
        claims.append(Claim(field="emails", value=e, source=SOURCE,
                            method="pdf_contact_regex", confidence=0.85, raw=e))
    for p in _PHONE_RE.findall(text):
        if sum(c.isdigit() for c in p) >= 9:  # avoid matching years/ids
            claims.append(Claim(field="phones", value=p, source=SOURCE,
                                method="pdf_contact_regex", confidence=0.8, raw=p))
    for u in _URL_RE.findall(text):
        claims.append(Claim(field="links", value=u, source=SOURCE,
                            method="pdf_url_regex", confidence=0.8, raw=u))

    # Name: first non-empty line that is not a contact line (lower conf)
    for ln in nonempty[:5]:
        s = ln.strip()
        if _EMAIL_RE.search(s) or _PHONE_RE.search(s) or _URL_RE.search(s):
            continue
        if 1 <= len(s.split()) <= 4 and not any(c.isdigit() for c in s):
            claims.append(Claim(field="full_name", value=s, source=SOURCE,
                                method="pdf_first_line", confidence=0.5, raw=s))
            break

    # Section segmentation
    sections = _segment(lines)

    # Headline from summary section (first sentence) -> medium.
    if sections.get("summary"):
        head = " ".join(sections["summary"]).strip()
        head = re.split(r"(?<=[.!?])\s", head)[0][:160] if head else ""
        if head:
            claims.append(Claim(field="headline", value=head, source=SOURCE,
                                method="pdf_summary_section", confidence=0.55, raw=head))

    # Skills from skills section -> medium.
    if sections.get("skills"):
        blob = " ".join(sections["skills"])
        for s in re.split(r"[;,|•·•/]", blob):
            s = s.strip()
            if 1 <= len(s) <= 40 and s:
                claims.append(Claim(field="skills", value=s, source=SOURCE,
                                    method="pdf_skills_section", confidence=0.65, raw=s))

    # Experience: detect lines with a date range -> medium.
    for ln in sections.get("experience", []):
        m = _DATE_RANGE.search(ln)
        if m:
            before = ln[:m.start()].strip(" -|,")
            claims.append(Claim(
                field="experience",
                value={"company_title": before, "start": m.group(1), "end": m.group(2)},
                source=SOURCE, method="pdf_experience_heuristic", confidence=0.6, raw=ln))

    # Education: lines mentioning a degree keyword -> medium.
    for ln in sections.get("education", []):
        if re.search(r"\b(b\.?s|m\.?s|b\.?tech|m\.?tech|bachelor|master|ph\.?d|mba)\b", ln, re.I):
            year = re.search(r"(19|20)\d{2}", ln)
            claims.append(Claim(
                field="education",
                value={"text": ln.strip(), "end_year": year.group(0) if year else None},
                source=SOURCE, method="pdf_education_heuristic", confidence=0.55, raw=ln))

    if not claims:
        if diag is not None:
            diag.warn("parse_resume", "no_fields_extracted",
                      "resume text parsed but no fields could be extracted")
        return []
    return [SourceBlock(source=SOURCE, claims=claims)]


def _segment(lines: list[str]) -> dict[str, list[str]]:
    """Split resume lines into sections keyed by recognised headers."""
    header_lookup = {kw: name for name, kws in _SECTIONS.items() for kw in kws}
    out: dict[str, list[str]] = {}
    current: Optional[str] = None
    for ln in lines:
        key = ln.strip().lower().rstrip(":")
        if key in header_lookup and len(key) <= 30:
            current = header_lookup[key]
            out.setdefault(current, [])
            continue
        if current and ln.strip():
            out[current].append(ln.strip())
    return out
