"""Merge engine: many Claims -> one CanonicalProfile with value-level provenance.

Conflict policy (hybrid, confidence-weighted with a source prior):
  * Scalars: highest claim_score wins; deterministic tie-break. Rejected values are recorded as competitors so the choice is auditable.
  * List scalars (emails/phones): union + dedupe; each kept value gets its own provenance entry (value-level, not field-level).
  * Skills: union + dedupe, per-skill confidence + sources.
  * Location: each sub-field (city/region/country) resolved independently.
  * Experience: matched on company + title similarity + date overlap/adjacency (distinct stints at the same employer stay separate)

Confidence is folded into each provenance entry.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from .models import (
    Claim, CanonicalProfile, Location, Links, Skill, Experience, Education,
    ValueProvenance, Competitor,
)
from . import confidence as conf
from .normalize.text import company_key


def merge(claims: list[Claim]) -> CanonicalProfile:
    by_field: dict[str, list[Claim]] = defaultdict(list)
    for c in claims:
        by_field[c.field].append(c)

    vp: list[ValueProvenance] = []
    field_confs: list[float] = []
    profile = CanonicalProfile(candidate_id="")

    # ---- scalar fields ----
    for field, attr in (("full_name", "full_name"),
                        ("headline", "headline"),
                        ("years_experience", "years_experience")):
        entry = _resolve_scalar(field, by_field.get(field, []))
        if entry is not None:
            setattr(profile, attr, entry.value)
            vp.append(entry)
            field_confs.append(entry.confidence)

    # ---- list scalar fields ----
    for field in ("emails", "phones"):
        values, entries = _resolve_list(field, by_field.get(field, []))
        if values:
            setattr(profile, field, values)
            vp.extend(entries)
            field_confs.append(round(sum(e.confidence for e in entries) / len(entries), 3))

    # ---- skills ----
    skills, entries = _resolve_skills(by_field.get("skills", []))
    if skills:
        profile.skills = skills
        vp.extend(entries)
        field_confs.append(round(sum(s.confidence for s in skills) / len(skills), 3))

    # ---- location (per sub-field) ----
    loc, entries = _resolve_location(by_field.get("location", []))
    if any([loc.city, loc.region, loc.country]):
        profile.location = loc
        vp.extend(entries)
        if entries:
            field_confs.append(round(sum(e.confidence for e in entries) / len(entries), 3))

    # ---- links ----
    links, entries = _resolve_links(by_field.get("links", []))
    if any([links.linkedin, links.github, links.portfolio, links.other]):
        profile.links = links
        vp.extend(entries)

    # ---- experience / education ----
    exp, entries = _resolve_experience(by_field.get("experience", []))
    if exp:
        profile.experience = exp
        vp.extend(entries)
        if entries:
            field_confs.append(round(max(e.confidence for e in entries), 3))

    edu, entries = _resolve_education(by_field.get("education", []))
    if edu:
        profile.education = edu
        vp.extend(entries)
        if entries:
            field_confs.append(round(max(e.confidence for e in entries), 3))

    profile.value_provenance = vp
    profile.overall_confidence = conf.overall(field_confs)
    profile.candidate_id = _candidate_id(profile)
    return profile


# ---------------------------------------------------------------------------
def _competitors(winner_value, claims: list[Claim], winner_score: float) -> list[Competitor]:
    """One competitor per distinct rejected value, best representative first."""
    comps, seen = [], set()
    for c in sorted(claims, key=lambda c: (-conf.claim_score(c), c.source, str(c.value))):
        if str(c.value) == str(winner_value):
            continue
        key = str(c.value).lower()
        if key in seen:
            continue
        seen.add(key)
        sc = round(conf.claim_score(c), 3)
        comps.append(Competitor(
            value=c.value, source=c.source, method=c.method, score=sc,
            rejected_because=f"lower evidence score {sc:.2f} < {winner_score:.2f}"))
    return comps


def _resolve_scalar(field: str, claims: list[Claim]) -> Optional[ValueProvenance]:
    if not claims:
        return None
    ranked = sorted(claims, key=lambda c: (-conf.claim_score(c), c.source, str(c.value)))
    winner = ranked[0]
    supporters = [c for c in claims if str(c.value) == str(winner.value)]
    had_conflict = len({str(c.value) for c in claims}) > 1
    score, factors, reason = conf.explain(supporters, had_conflict)
    src = "merged" if len({c.source for c in supporters}) > 1 else winner.source
    return ValueProvenance(
        field=field, value=winner.value, source=src, method=winner.method,
        confidence=score, reason=reason, factors=factors,
        competitors=_competitors(winner.value, claims, conf.claim_score(winner)))


def _resolve_list(field: str, claims: list[Claim]):
    """Union + dedupe; each kept value gets value-level provenance."""
    groups: dict[str, list[Claim]] = {}
    order: list[str] = []
    for c in sorted(claims, key=lambda c: (-conf.claim_score(c), c.source)):
        key = str(c.value).lower()
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(c)
    values, entries = [], []
    for key in order:
        grp = groups[key]
        best = grp[0]
        values.append(best.value)
        score, factors, reason = conf.explain(grp, had_conflict=False)
        src = "merged" if len({c.source for c in grp}) > 1 else best.source
        entries.append(ValueProvenance(field=field, value=best.value, source=src,
                                       method=best.method, confidence=score,
                                       reason=reason, factors=factors))
    return values, entries


def _resolve_skills(claims: list[Claim]):
    agg: dict[str, list[Claim]] = {}
    for c in claims:
        agg.setdefault(c.value.lower(), []).append(c)
    skills, entries = [], []
    for key in sorted(agg):
        grp = agg[key]
        name = grp[0].value
        score, factors, reason = conf.explain(grp, had_conflict=False)
        sources = sorted({c.source for c in grp})
        skills.append(Skill(name=name, confidence=score, sources=sources))
        entries.append(ValueProvenance(field=f"skills.{name}", value=name,
                                       source="merged" if len(sources) > 1 else sources[0],
                                       method=grp[0].method, confidence=score,
                                       reason=reason, factors=factors))
    return skills, entries


def _resolve_location(claims: list[Claim]):
    loc = Location()
    entries = []
    for sub in ("city", "region", "country"):
        sub_claims = [c for c in claims if isinstance(c.value, dict) and c.value.get(sub)]
        if not sub_claims:
            continue
        ranked = sorted(sub_claims, key=lambda c: (-conf.claim_score(c), c.source, str(c.value[sub])))
        w = ranked[0]
        supporters = [c for c in sub_claims if c.value[sub] == w.value[sub]]
        had_conflict = len({c.value[sub] for c in sub_claims}) > 1
        score, factors, reason = conf.explain(supporters, had_conflict)
        setattr(loc, sub, w.value[sub])
        comps = []
        for c in ranked[1:]:
            if c.value[sub] != w.value[sub]:
                sc = round(conf.claim_score(c), 3)
                comps.append(Competitor(value=c.value[sub], source=c.source, method=c.method,
                                        score=sc, rejected_because="lower evidence score"))
        entries.append(ValueProvenance(field=f"location.{sub}", value=w.value[sub],
                                       source="merged" if len({c.source for c in supporters}) > 1 else w.source,
                                       method=w.method, confidence=score, reason=reason,
                                       factors=factors, competitors=comps))
    return loc, entries


def _resolve_links(claims: list[Claim]):
    links = Links()
    entries = []
    seen_other = set()
    for c in sorted(claims, key=lambda c: (-conf.claim_score(c), c.source, str(c.value))):
        v = c.value
        if not isinstance(v, dict):
            continue
        kind, url = v.get("kind"), v.get("url")
        target = None
        if kind == "linkedin" and not links.linkedin:
            links.linkedin = url; target = "links.linkedin"
        elif kind == "github" and not links.github:
            links.github = url; target = "links.github"
        elif kind == "portfolio" and not links.portfolio:
            links.portfolio = url; target = "links.portfolio"
        elif url and url not in seen_other:
            links.other.append(url); seen_other.add(url); target = "links.other"
        if target:
            score, factors, reason = conf.explain([c], had_conflict=False)
            entries.append(ValueProvenance(field=target, value=url, source=c.source,
                                           method=c.method, confidence=score,
                                           reason=reason, factors=factors))
    return links, entries


# ---------------------------------------------------------------------------
# Experience: company + title + date-aware matching
# ---------------------------------------------------------------------------
def _month_int(m: Optional[str]) -> Optional[int]:
    if not m:
        return None
    if m == "present":
        return 9_999_999
    try:
        y, mo = m.split("-")
        return int(y) * 12 + int(mo)
    except (ValueError, AttributeError):
        return None


def _title_similarity(a: Optional[str], b: Optional[str]) -> float:
    if not a or not b:
        return 1.0  # missing title shouldn't block a merge
    ta, tb = set(a.lower().split()), set(b.lower().split())
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


def _dates_compatible(v: dict, e: dict) -> bool:
    """True if two periods overlap, are adjacent (<=1 month gap), or either lacks
    dates (can't prove they're distinct -> allow merge)."""
    a_s, a_e = _month_int(v.get("start")), _month_int(v.get("end"))
    b_s, b_e = _month_int(e.get("start")), _month_int(e.get("end"))
    if None in (a_s, a_e, b_s, b_e):
        return True
    if a_s <= b_e and b_s <= a_e:       # overlap
        return True
    gap = max(a_s - b_e, b_s - a_e)     # otherwise measure the gap
    return gap <= 1


def _same_job(v: dict, e: dict) -> bool:
    ck_v, ck_e = company_key(v.get("company")), company_key(e.get("company"))
    if ck_v and ck_e:
        if ck_v != ck_e:
            return False                # different employers -> never merge
        return _dates_compatible(v, e)  # same employer only if periods line up
    # One side has no company name: require strong title match + compatible dates.
    return _title_similarity(v.get("title"), e.get("title")) >= 0.6 and _dates_compatible(v, e)


def _resolve_experience(claims: list[Claim]):
    # Process best-evidence first so higher-score values win field fills.
    ordered = sorted([c for c in claims if isinstance(c.value, dict)],
                     key=lambda c: (-conf.claim_score(c), c.source))
    entries: list[dict] = []   # each: {fields..., _claims:[...]}
    for c in ordered:
        v = c.value
        placed = False
        for e in entries:
            if _same_job(v, e):
                _absorb(e, v, c)
                placed = True
                break
        if not placed:
            entries.append(_new_exp(v, c))

    exp_objs, vps = [], []
    for i, e in enumerate(entries):
        exp_objs.append(Experience(company=e["company"], title=e["title"],
                                   start=e["start"], end=e["end"], summary=e["summary"]))
        grp = e["_claims"]
        score, factors, reason = conf.explain(grp, had_conflict=False)
        sources = sorted({c.source for c in grp})
        reason = f"merged from {len(grp)} observation(s) [{', '.join(sources)}] matched by company+dates; " + reason
        vps.append(ValueProvenance(field=f"experience[{i}]", value=exp_objs[i].model_dump(),
                                   source="merged" if len(sources) > 1 else sources[0],
                                   method=grp[0].method, confidence=score,
                                   reason=reason, factors=factors))
    return exp_objs, vps


def _new_exp(v: dict, c: Claim) -> dict:
    return {"company": v.get("company"), "title": v.get("title"),
            "start": v.get("start"), "end": v.get("end"),
            "summary": v.get("summary"), "_claims": [c]}


def _absorb(e: dict, v: dict, c: Claim) -> None:
    # company/title/summary: fill if empty (claims arrive best-score-first).
    for f in ("company", "title", "summary"):
        if not e[f] and v.get(f):
            e[f] = v[f]
    # dates: widen to the union (earliest start, latest end) across sources.
    e["start"] = _earlier(e["start"], v.get("start"))
    e["end"] = _later(e["end"], v.get("end"))
    e["_claims"].append(c)


def _earlier(a: Optional[str], b: Optional[str]) -> Optional[str]:
    ia, ib = _month_int(a), _month_int(b)
    if ia is None:
        return b
    if ib is None:
        return a
    return a if ia <= ib else b


def _later(a: Optional[str], b: Optional[str]) -> Optional[str]:
    ia, ib = _month_int(a), _month_int(b)
    if ia is None:
        return b
    if ib is None:
        return a
    return a if ia >= ib else b


def _resolve_education(claims: list[Claim]):
    buckets: dict[str, list[Claim]] = {}
    order: list[str] = []
    for c in sorted([c for c in claims if isinstance(c.value, dict)],
                    key=lambda c: (-conf.claim_score(c), c.source)):
        v = c.value
        key = (v.get("institution") or v.get("degree") or str(len(order))).lower()
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(c)
    edu_objs, vps = [], []
    for i, key in enumerate(order):
        grp = buckets[key]
        merged = {"institution": None, "degree": None, "field": None, "end_year": None}
        for c in grp:
            for f in merged:
                if not merged[f] and c.value.get(f):
                    merged[f] = c.value[f]
        edu_objs.append(Education(**merged))
        score, factors, reason = conf.explain(grp, had_conflict=False)
        sources = sorted({c.source for c in grp})
        vps.append(ValueProvenance(field=f"education[{i}]", value=merged,
                                   source="merged" if len(sources) > 1 else sources[0],
                                   method=grp[0].method, confidence=score,
                                   reason=reason, factors=factors))
    return edu_objs, vps


def _candidate_id(p: CanonicalProfile) -> str:
    import hashlib
    seed = (p.emails[0] if p.emails else (p.full_name or "unknown")).lower()
    return f"cand_{hashlib.sha1(seed.encode()).hexdigest()[:10]}"
