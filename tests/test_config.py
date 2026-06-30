"""Config schema validation: good configs load, bad ones fail fast & clearly."""

import json
import os
import pytest

from src.config import load_config, default_config, ConfigError

ROOT = os.path.join(os.path.dirname(__file__), "..")


def test_shipped_configs_are_valid():
    for name in ("default.json", "custom.json", "full_provenance.json"):
        cfg = load_config(os.path.join(ROOT, "config", name))
        assert "on_missing" in cfg


def test_missing_file_falls_back_to_defaults():
    cfg = load_config("/does/not/exist.json")
    assert cfg == default_config()


def test_from_alias_survives_round_trip():
    # the 'from' key (a Python keyword) must come back as 'from', not 'from_'
    cfg = load_config(os.path.join(ROOT, "config", "custom.json"))
    paths = {f["path"]: f for f in cfg["fields"]}
    assert paths["primary_email"]["from"] == "emails[0]"


def test_unknown_key_is_rejected(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"on_missing": "null", "include_confidance": True}))  # typo
    with pytest.raises(ConfigError):
        load_config(str(bad))


def test_bad_enum_value_is_rejected(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"on_missing": "explode"}))
    with pytest.raises(ConfigError):
        load_config(str(bad))


def test_malformed_json_is_rejected(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json")
    with pytest.raises(ConfigError):
        load_config(str(bad))
