"""
Deterministic identity resolution using weighted evidence.

It scores several independent signals (email, phone, name, company, school,
location) instead of trusting a single field. Email and phone are treated as
strong evidence, while name and profile attributes are only supporting signals,
which keeps false merges rare.

Thresholds:
- >= 0.90: automatic merge
- 0.50–0.90: ambiguous (requires review)
- < 0.50: no merge

(intentionally conservative because merging two different
people is more costly than leaving duplicate records)

Scale: candidates are first bucketed by shared keys (email, phone, name, company, school).
Avoids an O(n^2) scan over all candidates.
"""

from __future__ import annotations

from itertools import combinations

from .models import SourceBlock
from .normalize.text import company_key, normalize_name
from .diagnostics import Diagnostics

W_EMAIL = 1.00
W_PHONE = 0.90
W_NAME_EXACT = 0.40
W_NAME_FUZZY = 0.20
W_COMPANY = 0.20
W_EDU = 0.20
W_LOCATION = 0.10

AUTO = 0.90
AMBIGUOUS = 0.50


def _signals(block: SourceBlock) -> dict:
    emails, phones, names, companies, schools = set(), set(), set(), set(), set()
    locations = set()
    for c in block.claims:
        if c.field == "emails":
            emails.add(str(c.value).lower())
        elif c.field == "phones":
            phones.add(str(c.value))
        elif c.field == "full_name":
            nn = normalize_name(c.value)
            if nn:
                names.add(nn.lower())
        elif c.field == "experience" and isinstance(c.value, dict):
            ck = company_key(c.value.get("company"))
            if ck:
                companies.add(ck)
        elif c.field == "education" and isinstance(c.value, dict):
            inst = c.value.get("institution")
            if inst:
                schools.add(inst.lower())
        elif c.field == "location" and isinstance(c.value, dict):
            locations.add((c.value.get("city"), c.value.get("country")))
    return {"emails": emails, "phones": phones, "names": names,
            "companies": companies, "schools": schools, "locations": locations}


def _name_match(a: set, b: set) -> float:
    if a & b:
        return W_NAME_EXACT
    # fuzzy: token overlap (Jaccard) over the best name pair
    best = 0.0
    for x in a:
        for y in b:
            tx, ty = set(x.split()), set(y.split())
            if tx and ty:
                best = max(best, len(tx & ty) / len(tx | ty))
    return W_NAME_FUZZY if best >= 0.5 else 0.0


def _score(sa: dict, sb: dict) -> tuple[float, list[str], bool]:
    score = 0.0
    matched: list[str] = []
    decisive = False
    if sa["emails"] & sb["emails"]:
        score += W_EMAIL; matched.append("email"); decisive = True
    if sa["phones"] & sb["phones"]:
        score += W_PHONE; matched.append("phone"); decisive = True
    nm = _name_match(sa["names"], sb["names"])
    if nm:
        score += nm; matched.append("name")
    if sa["companies"] & sb["companies"]:
        score += W_COMPANY; matched.append("company")
    if sa["schools"] & sb["schools"]:
        score += W_EDU; matched.append("school")
    common_loc = {l for l in (sa["locations"] & sb["locations"]) if any(l)}
    if common_loc:
        score += W_LOCATION; matched.append("location")
    return round(score, 3), matched, decisive


def group(blocks: list[SourceBlock], diag: Diagnostics | None = None) -> list[list[SourceBlock]]:
    """Cluster blocks into per-person groups: bucket by shared keys, then score
    only the pairs that land in the same bucket."""
    n = len(blocks)
    sigs = [_signals(b) for b in blocks]
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    # Blocking: only compare candidates that share a cheap key (email, phone, name, company or school). 
    # A pair that shares no key cannot reach the match threshold, so skipping it is safe. 
    buckets: dict[str, list[int]] = {}
    for idx, sg in enumerate(sigs):
        for v in sg["emails"]:    buckets.setdefault(f"e:{v}", []).append(idx)
        for v in sg["phones"]:    buckets.setdefault(f"p:{v}", []).append(idx)
        for v in sg["names"]:     buckets.setdefault(f"n:{v}", []).append(idx)
        for v in sg["companies"]: buckets.setdefault(f"c:{v}", []).append(idx)
        for v in sg["schools"]:   buckets.setdefault(f"s:{v}", []).append(idx)

    candidate_pairs: set[tuple[int, int]] = set()
    for members in buckets.values():
        for i, j in combinations(sorted(set(members)), 2):
            candidate_pairs.add((i, j))

    # Deterministic: process the blocked pairs in sorted order.
    for i, j in sorted(candidate_pairs):
        score, matched, decisive = _score(sigs[i], sigs[j])
        if score >= AUTO:
            union(i, j)
            if not decisive and diag is not None:
                diag.warn("identity", "low_confidence_merge",
                          f"merged records {i} and {j} on corroboration without "
                          f"email/phone (score {score}, signals {matched})",
                          score=score, signals=matched)
        elif score >= AMBIGUOUS and diag is not None:
            diag.warn("identity", "ambiguous_match",
                      f"records {i} and {j} look similar (score {score}, signals "
                      f"{matched}) but were NOT merged; review recommended",
                      score=score, signals=matched)

    groups: dict[int, list[SourceBlock]] = {}
    for idx in range(n):
        groups.setdefault(find(idx), []).append(blocks[idx])
    return [g for _, g in sorted(groups.items())]
