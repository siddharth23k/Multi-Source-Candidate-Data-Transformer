"""Runtime output config: loading + validation.

The config reshapes the output only; the internal canonical record is always built the same
way. This keeps a clean separation between what is known about the candidate and what a
particular consumer wants to see.

A missing config file is fine ( fall back to defaults).
A present but invalid one is a caller error and is raised loudly.

Schema:
{
  "fields": [
     {"path": "<output key>", "from": "<canonical path>", "type": "<type>",
      "required": <bool>, "normalize": "E164"|"canonical"}
  ],
  "include_confidence": <bool>,         # default true
  "include_provenance": <bool>,         # default true
  "provenance_detail": "compact"|"full",# default "compact"
  "on_missing": "null"|"omit"|"error"   # default "null"
}
If "fields" is absent, the full default schema is emitted.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError as PydanticValidationError

log = logging.getLogger("pipeline.config")


class ConfigError(Exception):
    """Raised when a config file exists but does not match the schema."""


class FieldSpec(BaseModel):
    # extra="forbid" turns an unexpected key (often a typo like "form" for "from")
    # into an error instead of a silently ignored field.
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    path: str
    from_: Optional[str] = Field(default=None, alias="from")
    type: Optional[Literal["string", "string[]", "number", "int"]] = None
    required: bool = False
    normalize: Optional[Literal["E164", "canonical"]] = None


class OutputConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    fields: Optional[list[FieldSpec]] = None
    include_confidence: bool = True
    include_provenance: bool = True
    provenance_detail: Literal["compact", "full"] = "compact"
    on_missing: Literal["null", "omit", "error"] = "null"


# Convert the validated model back to the dict format expected downstream.
def _to_dict(cfg: OutputConfig) -> dict:
    return cfg.model_dump(by_alias=True, exclude_none=True)


def default_config() -> dict:
    return _to_dict(OutputConfig())


def load_config(path: Optional[str]) -> dict:
    if not path:
        return default_config()
    if not os.path.exists(path):
        log.warning("config %s not found; using defaults", path)
        return default_config()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise ConfigError(f"could not read config {path}: {e}") from e
    try:
        cfg = OutputConfig.model_validate(raw or {})
    except PydanticValidationError as e:
        raise ConfigError(f"invalid config {path}:\n{e}") from e
    return _to_dict(cfg)
