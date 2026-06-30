"""Country -> ISO-3166 alpha-2, and location string parsing.

Supports both Indian and US/UK locations. Indian states are matched by full name
(e.g. "Karnataka") to avoid 2-letter collisions with US state codes."""

from __future__ import annotations

import re
from typing import Optional

# Small lookup table. In production this would be a full dataset (pycountry).
_COUNTRY = {
    "united states": "US", "usa": "US", "us": "US", "u.s.": "US",
    "u.s.a.": "US", "america": "US",
    "india": "IN", "bharat": "IN",
    "united kingdom": "GB", "uk": "GB", "england": "GB", "britain": "GB",
    "canada": "CA", "germany": "DE", "deutschland": "DE", "france": "FR",
    "australia": "AU", "singapore": "SG", "ireland": "IE", "netherlands": "NL",
}

# US state abbreviations -> implies country US (helps "San Francisco, CA").
_US_STATES = {
    "al","ak","az","ar","ca","co","ct","de","fl","ga","hi","id","il","in","ia",
    "ks","ky","la","me","md","ma","mi","mn","ms","mo","mt","ne","nv","nh","nj",
    "nm","ny","nc","nd","oh","ok","or","pa","ri","sc","sd","tn","tx","ut","vt",
    "va","wa","wv","wi","wy",
}

# Indian states & UTs by FULL NAME -> implies country IN (helps "Bengaluru, Karnataka"). 
_INDIA_STATES = {
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh",
    "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand", "karnataka",
    "kerala", "madhya pradesh", "maharashtra", "manipur", "meghalaya", "mizoram",
    "nagaland", "odisha", "punjab", "rajasthan", "sikkim", "tamil nadu",
    "telangana", "tripura", "uttar pradesh", "uttarakhand", "west bengal",
    "delhi", "new delhi", "jammu and kashmir", "ladakh", "puducherry",
    "chandigarh",
}


def normalize_country(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.strip().lower().rstrip(".")
    # Alias map first so 'uk' -> 'GB' rather than the literal 'UK'.
    if v in _COUNTRY:
        return _COUNTRY[v]
    # Otherwise accept an explicit 2-letter ISO code (e.g. 'JP', 'BR').
    if len(v) == 2 and v.isalpha():
        return v.upper()
    return None


def parse_location(value: Optional[str]) -> dict:
    """Parse 'City, Region, Country' style strings into a dict.
    Returns {city, region, country}; any unknown part stays None."""
    out = {"city": None, "region": None, "country": None}
    if not value:
        return out
    parts = [p.strip() for p in re.split(r"[,/|]", value) if p.strip()]
    if not parts:
        return out

    last = parts[-1].lower()
    # A US state code as the last part implies region + country US. 
    # check this before country resolution so 'CA' reads as California, not Canada.
    if last in _US_STATES:
        out["region"] = parts[-1].upper()
        out["country"] = "US"
        parts = parts[:-1]
    # An Indian state name as the last part implies region + country IN.
    elif last in _INDIA_STATES:
        out["region"] = parts[-1]
        out["country"] = "IN"
        parts = parts[:-1]
    elif normalize_country(parts[-1]):
        out["country"] = normalize_country(parts[-1])
        parts = parts[:-1]
        # A remaining trailing part may still be a region/state name.
        if len(parts) >= 2:
            out["region"] = parts[-1]
            parts = parts[:-1]

    if parts:
        out["city"] = parts[0]
    return out
