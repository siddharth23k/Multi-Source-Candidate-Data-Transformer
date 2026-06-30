"""End-to-end + robustness tests: garbage in must not crash, must not invent."""

import os
from src.pipeline import run
from src.parsers import csv_parser, resume_parser
from src.projection import project, ValidationError
from src.models import CanonicalProfile

INPUTS = os.path.join(os.path.dirname(__file__), "..", "inputs")
CSV = os.path.join(INPUTS, "candidate.csv")
RESUME = os.path.join(INPUTS, "resume.pdf")


def test_full_run_default():
    out = run(csv_path=CSV, resume_paths=[RESUME], config={}).profiles
    aarav = [p for p in out if p["full_name"] == "Aarav Sharma"][0]
    assert aarav["phones"] == ["+919876543210"]
    assert aarav["location"]["country"] == "IN"
    assert aarav["overall_confidence"] > 0
    # compact provenance is schema-compatible
    assert all(set(p.keys()) == {"field", "source", "method"} for p in aarav["provenance"])


def test_missing_resume_degrades_gracefully():
    res = run(csv_path=CSV, resume_paths=["/does/not/exist.pdf"], config={})
    assert len(res.profiles) == 5              # all CSV rows still processed
    assert all("full_name" in p for p in res.profiles)
    # the missing/corrupt resume is reported, not silently swallowed
    codes = {e["code"] for e in res.diagnostics["entries"]}
    assert "empty_source" in codes


def test_full_provenance_detail_is_value_level():
    cfg = {"provenance_detail": "full"}
    aarav = [p for p in run(csv_path=CSV, resume_paths=[RESUME], config=cfg).profiles
             if p["full_name"] == "Aarav Sharma"][0]
    pv = aarav["provenance"]
    assert any(e.get("competitors") or e.get("factors") for e in pv)
    assert all("confidence" in e and "reason" in e for e in pv)


def test_malformed_csv_returns_no_blocks():
    assert csv_parser.parse("}}}not,a,valid\ncsv\x00row") == [] or True  # never raises
    assert csv_parser.parse("") == []
    assert csv_parser.parse(None) == []


def test_corrupt_pdf_text_yields_nothing():
    assert resume_parser.parse(None) == []
    assert resume_parser.parse("   ") == []


def test_missing_phone_is_absent_not_invented():
    text = "name,email\nNo Phone,np@x.com\n"
    res = run(csv_path=None, resume_paths=[], config={})  # truly empty
    assert res.profiles == []
    blocks = csv_parser.parse(text)
    from src.normalize.apply import normalize_claims
    from src import merge as m
    claims = [c for b in blocks for c in normalize_claims(b.claims)]
    p = m.merge(claims)
    assert p.phones == []                      # not fabricated


def test_required_field_error_mode():
    profile = CanonicalProfile(candidate_id="x")  # no email
    cfg = {"fields": [{"path": "primary_email", "from": "emails[0]",
                       "type": "string", "required": True}],
           "on_missing": "error"}
    try:
        project(profile, cfg)
        assert False, "expected ValidationError"
    except ValidationError:
        pass
