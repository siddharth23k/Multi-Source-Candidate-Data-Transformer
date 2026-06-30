"""Identity scoring: never merge on name alone; merge on decisive signals."""

from src.models import Claim, SourceBlock
from src.normalize.apply import normalize_claims
from src import identity
from src.diagnostics import Diagnostics


def _block(source, **fields):
    claims = []
    for f, vals in fields.items():
        for v in (vals if isinstance(vals, list) else [vals]):
            claims.append(Claim(field=f, value=v, source=source,
                                method="test", confidence=0.9))
    return SourceBlock(source=source, claims=normalize_claims(claims))


def test_same_email_auto_merges():
    a = _block("recruiter_csv", full_name="Jane Doe", emails="jane@x.com")
    b = _block("resume_pdf", full_name="J Doe", emails="jane@x.com")
    groups = identity.group([a, b])
    assert len(groups) == 1


def test_name_alone_never_merges():
    a = _block("recruiter_csv", full_name="John Smith", emails="john1@x.com")
    b = _block("resume_pdf", full_name="John Smith", emails="john2@y.com")
    groups = identity.group([a, b])
    assert len(groups) == 2          # two different John Smiths stay separate


def test_ambiguous_match_reported_not_merged():
    diag = Diagnostics()
    a = _block("recruiter_csv", full_name="Jane Doe", emails="a@x.com",
               experience={"company": "Google"}, location={"city": "SF", "country": "US"})
    b = _block("recruiter_csv", full_name="Jane Doe", emails="b@y.com",
               experience={"company": "Google"}, location={"city": "SF", "country": "US"})
    groups = identity.group([a, b], diag=diag)
    assert len(groups) == 2
    assert any(e["code"] == "ambiguous_match" for e in diag.entries)


def test_phone_is_decisive():
    a = _block("recruiter_csv", full_name="A", phones="+14155552671")
    b = _block("resume_pdf", full_name="B", phones="+14155552671")
    assert len(identity.group([a, b])) == 1


def test_blocking_preserves_grouping_at_scale():
    # Many distinct people + one cross-source duplicate. Blocking must still
    # merge the duplicate and keep everyone else separate.
    blocks = []
    for i in range(50):
        blocks.append(_block("recruiter_csv", full_name=f"Person {i}",
                             emails=f"person{i}@x.com"))
    # the duplicate: same email as Person 0, from the other source
    blocks.append(_block("resume_pdf", full_name="Person Zero", emails="person0@x.com"))
    groups = identity.group(blocks)
    assert len(groups) == 50                 # 51 records -> 50 people
    merged = [g for g in groups if len(g) == 2]
    assert len(merged) == 1                  # exactly one pair merged
