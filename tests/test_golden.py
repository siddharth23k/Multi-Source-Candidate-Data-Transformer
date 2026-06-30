"""Golden-output test: locks the full pipeline output byte-for-byte.

The pipeline must be deterministic (same input -> same output), so this test compares a fresh
run against a saved expected result. Any accidental change shows up as a diff.

To refresh after an intended change:
    python -c "import json; from src.config import load_config; from src.pipeline import run; \
        json.dump(run(csv_path='inputs/candidate.csv', resume_paths=['inputs/resume.pdf'], \
        config=load_config('config/default.json')).profiles, \
        open('tests/golden/default_profiles.json','w'), indent=2, ensure_ascii=False)"
"""

import json
import os

from src.config import load_config
from src.pipeline import run

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..")
GOLDEN = os.path.join(HERE, "golden", "default_profiles.json")


def _run():
    res = run(csv_path=os.path.join(ROOT, "inputs", "candidate.csv"),
              resume_paths=[os.path.join(ROOT, "inputs", "resume.pdf")],
              config=load_config(os.path.join(ROOT, "config", "default.json")))
    return res.profiles


def test_matches_golden():
    with open(GOLDEN, encoding="utf-8") as f:
        expected = json.load(f)
    assert _run() == expected


def test_deterministic_across_runs():
    # Same input twice -> byte-for-byte identical serialization.
    a = json.dumps(_run(), sort_keys=True)
    b = json.dumps(_run(), sort_keys=True)
    assert a == b
