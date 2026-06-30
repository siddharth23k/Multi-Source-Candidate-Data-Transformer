"""Phone normalization to E.164 using Google's libphonenumber port."""

from __future__ import annotations

from typing import Optional
import phonenumbers


def normalize_phone(value: Optional[str], default_region: str = "IN") -> Optional[str]:
    """Return E.164 (e.g. '+919876543210') or None if not a valid number.

    default_region is used when the raw number has no country code. Choose it
    based on the candidate's location if known; default to IN (India)
    and the pipeline overrides it per-candidate from their location.
    """
    if not value:
        return None
    try:
        parsed = phonenumbers.parse(value, default_region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
