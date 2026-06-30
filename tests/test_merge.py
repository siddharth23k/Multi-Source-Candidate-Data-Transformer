from src.models import Claim
from src.normalize.apply import normalize_claims
from src import merge as merge_mod


def _norm(claims):
    return normalize_claims(claims)


def test_scalar_winner_prefers_reliable_source():
    # CSV (reliability 0.90) vs resume (0.75) disagree on the name.
    claims = _norm([
        Claim(field="full_name", value="Jane Doe", source="recruiter_csv",
              method="csv_cell", confidence=0.9),
        Claim(field="full_name", value="Jane D", source="resume_pdf",
              method="pdf_first_line", confidence=0.5),
    ])
    p = merge_mod.merge(claims)
    assert p.full_name == "Jane Doe"
    # value-level provenance records the winner and the rejected competitor.
    fn = [vp for vp in p.value_provenance if vp.field == "full_name"][0]
    assert any(comp.value == "Jane D" for comp in fn.competitors)
    assert "conflict" in fn.reason


def test_company_variants_merge_into_one_experience():
    claims = _norm([
        Claim(field="experience", value={"company": "Google", "title": "SWE"},
              source="recruiter_csv", method="csv_cell", confidence=0.9),
        Claim(field="experience",
              value={"company_title": "Senior SWE at Google LLC",
                     "start": "Jan 2021", "end": "Present"},
              source="resume_pdf", method="pdf_experience_heuristic", confidence=0.6),
    ])
    p = merge_mod.merge(claims)
    companies = [e.company for e in p.experience]
    assert companies.count("Google") + companies.count("Google LLC") == 1  # not duplicated
    assert p.experience[0].start == "2021-01"


def test_agreement_boosts_skill_confidence():
    claims = _norm([
        Claim(field="skills", value="python", source="recruiter_csv",
              method="csv_cell", confidence=0.9),
        Claim(field="skills", value="Python", source="resume_pdf",
              method="pdf_skills_section", confidence=0.65),
    ])
    p = merge_mod.merge(claims)
    py = [s for s in p.skills if s.name == "Python"][0]
    assert set(py.sources) == {"recruiter_csv", "resume_pdf"}
    assert py.confidence > 0.81   # agreement bonus applied


def test_deterministic_candidate_id():
    claims = _norm([Claim(field="emails", value="a@b.com", source="recruiter_csv",
                          method="csv_cell", confidence=0.9)])
    assert merge_mod.merge(claims).candidate_id == merge_mod.merge(claims).candidate_id
