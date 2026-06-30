"""Apply per-field normalization to raw Claims.

Input: raw Claims straight from parsers (value is whatever the parser saw).
Output: normalized Claims with canonical-format values. Claims whose value cannot
be normalized are DROPPED (we never keep a value we could not make sense of).

The `phone_region` is configurable so the same engine works across countries
(it defaults to India and is overridden per-candidate from their location).
"""

from __future__ import annotations

import re
from typing import Optional

from ..models import Claim
from . import text as T
from .phone import normalize_phone
from .dates import normalize_month, normalize_year
from .country import parse_location
from .skills import canonical_skill


def normalize_claims(claims: list[Claim], phone_region: str = "IN", diag=None) -> list[Claim]:
    """Normalize every claim; drop (and report) ones that cannot be normalized."""
    out: list[Claim] = []
    for c in claims:
        nc = _normalize_one(c, phone_region)
        if nc is not None:
            out.append(nc)
        elif diag is not None:
            diag.warn("normalize", "dropped_value",
                      f"could not normalize {c.field}='{c.raw or c.value}' from {c.source}",
                      field=c.field, source=c.source, raw=c.raw or str(c.value))
    return out


def _normalize_one(c: Claim, phone_region: str) -> Optional[Claim]:
    f = c.field
    v = c.value

    if f == "full_name":
        nv = T.normalize_name(v)
    elif f == "emails":
        nv = T.normalize_email(v)
    elif f == "phones":
        nv = normalize_phone(v, phone_region)
    elif f == "skills":
        nv = canonical_skill(v)
    elif f == "years_experience":
        nv = _to_float(v)
    elif f == "headline":
        nv = T.clean_ws(v)
    elif f == "location":
        nv = _norm_location(v)
    elif f == "links":
        nv = _classify_link(v)
    elif f == "experience":
        nv = _norm_experience(v)
    elif f == "education":
        nv = _norm_education(v)
    else:
        nv = v

    if nv is None or (isinstance(nv, dict) and not any(nv.values())):
        return None
    return c.model_copy(update={"value": nv, "method": c.method + "+norm"})


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    m = re.search(r"\d+(\.\d+)?", str(v))
    return float(m.group(0)) if m else None


def _norm_location(v) -> Optional[dict]:
    if isinstance(v, dict):
        loc = {"city": v.get("city"), "region": v.get("region"), "country": v.get("country")}
    else:
        loc = parse_location(v)
    return loc if any(loc.values()) else None


def _classify_link(v: str) -> Optional[dict]:
    if not v:
        return None
    url = v.strip().rstrip("/,.")
    low = url.lower()
    if not low.startswith("http"):
        url = "https://" + url
    if "linkedin.com" in low:
        return {"kind": "linkedin", "url": url}
    if "github.com" in low:
        return {"kind": "github", "url": url}
    return {"kind": "other", "url": url}


def _norm_experience(v) -> Optional[dict]:
    if not isinstance(v, dict):
        return None
    company = v.get("company")
    title = v.get("title")
    # Resume gives a combined "company_title" string; split heuristically.
    if not company and v.get("company_title"):
        ct = v["company_title"]
        parts = re.split(r"\s+(?:at|@|[-–|,])\s+", ct, maxsplit=1)
        if len(parts) == 2:
            title, company = parts[0].strip(), parts[1].strip()
        else:
            company = ct.strip()
    out = {
        "company": T.clean_ws(company),
        "title": T.clean_ws(title),
        "start": normalize_month(v.get("start")) if v.get("start") else None,
        "end": normalize_month(v.get("end")) if v.get("end") else None,
        "summary": T.clean_ws(v.get("summary")),
    }
    return out if any(out.values()) else None


def _norm_education(v) -> Optional[dict]:
    if not isinstance(v, dict):
        return None
    if v.get("text"):
        txt = v["text"]
        deg = re.search(r"\b(b\.?s|m\.?s|b\.?tech|m\.?tech|bachelor[\w' ]*|master[\w' ]*|ph\.?d|mba)\b",
                        txt, re.I)
        out = {
            "institution": None,
            "degree": deg.group(0) if deg else None,
            "field": None,
            "end_year": normalize_year(v.get("end_year")) if v.get("end_year") else normalize_year(txt),
        }
        # Institution: longest comma-part that isn't the degree/year.
        parts = [p.strip() for p in re.split(r"[,|]", txt) if p.strip()]
        cand = [p for p in parts if not re.search(r"\d{4}", p) and (not deg or deg.group(0).lower() not in p.lower())]
        if cand:
            out["institution"] = max(cand, key=len)
        return out if any(out.values()) else None
    out = {
        "institution": T.clean_ws(v.get("institution")),
        "degree": T.clean_ws(v.get("degree")),
        "field": T.clean_ws(v.get("field")),
        "end_year": normalize_year(v.get("end_year")) if v.get("end_year") else None,
    }
    return out if any(out.values()) else None
