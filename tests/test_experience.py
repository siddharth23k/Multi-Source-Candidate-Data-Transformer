"""Experience merge: company + dates, not company alone."""

from src.models import Claim
from src.normalize.apply import normalize_claims
from src import merge as merge_mod


def _exp(value, source="recruiter_csv", conf=0.9):
    return Claim(field="experience", value=value, source=source, method="t", confidence=conf)


def _merge(claims):
    return merge_mod.merge(normalize_claims(claims))


def test_same_company_overlapping_dates_merge():
    p = _merge([
        _exp({"company": "Google", "title": "SWE"}),
        _exp({"company_title": "Senior SWE at Google LLC", "start": "Jan 2021", "end": "Present"},
             source="resume_pdf", conf=0.6),
    ])
    assert len(p.experience) == 1            # one job, complementary fields merged
    assert p.experience[0].start == "2021-01"


def test_same_company_separate_periods_stay_separate():
    # Two non-overlapping stints at the same employer (a rehire) must NOT collapse.
    p = _merge([
        _exp({"company": "Google", "title": "SWE", "start": "2015-01", "end": "2017-01"}),
        _exp({"company": "Google", "title": "Staff", "start": "2021-01", "end": "2023-01"}),
    ])
    assert len(p.experience) == 2


def test_different_companies_never_merge():
    p = _merge([
        _exp({"company": "Google", "title": "SWE", "start": "2021-01", "end": "2022-01"}),
        _exp({"company": "Stripe", "title": "SWE", "start": "2021-01", "end": "2022-01"}),
    ])
    assert len(p.experience) == 2
