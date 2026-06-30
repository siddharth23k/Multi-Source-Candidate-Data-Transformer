"""Projection + validation layer.

Takes the internal CanonicalProfile and a config dict
Produces the final output dict the consumer asked for.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .models import CanonicalProfile
from .normalize.phone import normalize_phone
from .normalize.skills import canonical_skill


class ValidationError(Exception):
    pass


def project(profile: CanonicalProfile, config: dict) -> dict:
    data = profile.model_dump()

    if config.get("fields"):
        out = _project_custom(data, config)
    else:
        out = _project_default(data, config)

    _validate(out, config)
    return out


# ---------------------------------------------------------------------------
def _flatten_field(field: str) -> str:
    """Maps value paths to top-level fields (e.g. 'location.country' -> 'location')."""
    return field.split("[")[0].split(".")[0]


def _provenance_output(data: dict, config: dict):
    """Build the provenance projection from the internal value_provenance."""
    rich = data.get("value_provenance", [])
    if config.get("provenance_detail") == "full":
        return rich
    # compact, schema-compatible: dedupe {field, source, method} preserving order.
    seen, out = set(), []
    for vp in rich:
        key = (_flatten_field(vp["field"]), vp["source"], vp["method"])
        if key in seen:
            continue
        seen.add(key)
        out.append({"field": key[0], "source": key[1], "method": key[2]})
    return out


def _project_default(data: dict, config: dict) -> dict:
    out = dict(data)
    out.pop("value_provenance", None)
    if config.get("include_provenance", True):
        out["provenance"] = _provenance_output(data, config)
    if not config.get("include_confidence", True):
        out.pop("overall_confidence", None)
        for s in out.get("skills", []):
            s.pop("confidence", None)
    return out


def _project_custom(data: dict, config: dict) -> dict:
    out: dict = {}
    on_missing = config.get("on_missing", "null")
    for spec in config["fields"]:
        out_key = spec["path"]
        src_path = spec.get("from", spec["path"])
        value = _resolve(data, src_path)

        if value is None or value == [] or value == "":
            if spec.get("required") and on_missing == "error":
                raise ValidationError(f"required field '{out_key}' is missing")
            if on_missing == "omit":
                continue
            out[out_key] = None
            continue

        value = _apply_normalize(value, spec.get("normalize"))
        value = _coerce(value, spec.get("type"))
        out[out_key] = value

    if config.get("include_confidence", True):
        out["overall_confidence"] = data.get("overall_confidence")
    if config.get("include_provenance", True):
        out["provenance"] = _provenance_output(data, config)
    return out


# ---------------------------------------------------------------------------
def _resolve(data: Any, path: str) -> Any:
    """Resolve dotted paths with list ops: 'a.b', 'list[0]', 'list[].name'."""
    return _resolve_tokens(data, path.split("."))


def _resolve_tokens(cur: Any, tokens: list) -> Any:
    if not tokens or cur is None:
        return cur
    token, rest = tokens[0], tokens[1:]
    m = re.fullmatch(r"([A-Za-z0-9_]+)(\[\d+\]|\[\])?", token)
    if not m:
        return None
    key, idx = m.group(1), m.group(2)
    cur = cur.get(key) if isinstance(cur, dict) else None
    if cur is None:
        return None
    if idx == "[]":
        if not isinstance(cur, list):
            return None
        return [_resolve_tokens(el, rest) for el in cur] if rest else cur
    if idx:  # [n]
        i = int(idx[1:-1])
        cur = cur[i] if isinstance(cur, list) and len(cur) > i else None
    return _resolve_tokens(cur, rest)


def _apply_normalize(value: Any, mode: Optional[str]) -> Any:
    if not mode:
        return value
    if mode == "E164":
        if isinstance(value, list):
            return [normalize_phone(v) or v for v in value]
        return normalize_phone(value) or value
    if mode == "canonical":
        if isinstance(value, list):
            return [canonical_skill(v) or v for v in value]
        return canonical_skill(value) or value
    return value


def _coerce(value: Any, type_str: Optional[str]) -> Any:
    if not type_str:
        return value
    try:
        if type_str == "string":
            return value if isinstance(value, list) else str(value)
        if type_str == "string[]":
            return value if isinstance(value, list) else [str(value)]
        if type_str == "number":
            return float(value)
        if type_str == "int":
            return int(value)
    except (TypeError, ValueError):
        return value
    return value


# ---------------------------------------------------------------------------
def _validate(out: dict, config: dict) -> None:
    """Validate the projected output against the requested field specs."""
    for spec in config.get("fields", []):
        key = spec["path"]
        if spec.get("required") and out.get(key) in (None, "", []):
            if config.get("on_missing") == "error":
                raise ValidationError(f"required field '{key}' missing after projection")
        t = spec.get("type")
        v = out.get(key)
        if v is None or t is None:
            continue
        if t == "string" and not isinstance(v, str):
            raise ValidationError(f"field '{key}' expected string, got {type(v).__name__}")
        if t == "string[]" and not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
            raise ValidationError(f"field '{key}' expected string[]")
        if t == "number" and not isinstance(v, (int, float)):
            raise ValidationError(f"field '{key}' expected number")
