"""Confidence engine.

A field's confidence answers: 'how much should a downstream system trust this
value?' three signals combined:

  base      = source_reliability(source) * parser_confidence   (how good is the best evidence for the chosen value)
  agreement = +bonus if two or more independent sources produced the same value
  conflict  = -penalty if other sources produced a different value that we had to reject

overall_confidence is the mean of the populated field confidences.
"""

from __future__ import annotations

from .models import Claim, SOURCE_RELIABILITY

AGREEMENT_BONUS = 0.10
CONFLICT_PENALTY = 0.15
CAP = 0.99


def _reliability(source: str) -> float:
    return SOURCE_RELIABILITY.get(source, 0.5)


def claim_score(c: Claim) -> float:
    """Score used to rank competing claims (deterministic winner selection)."""
    return _reliability(c.source) * c.confidence


def explain(winners: list[Claim], had_conflict: bool) -> tuple[float, dict, str]:
    """Return (confidence, factors, human-readable reason).

    Confidence is built from three justified terms:
      * base = best (source_reliability x parser_confidence) among supporting
        claims. Rationale: trust is bounded by both how good the source is and how
        sure the parser was; the product captures 'good source, weak extraction'.
      * +AGREEMENT_BONUS when >=2 independent sources produced the same value.
        Rationale: independent corroboration is real evidence, but bounded so a
        single strong source can still outrank two weak agreeing ones.
      * -CONFLICT_PENALTY when another source produced a different value that was
        rejected. Rationale: 'wrong-but-confident' is worse than 'honestly-empty'.
    """
    if not winners:
        return 0.0, {}, "no supporting evidence"
    base = max(claim_score(c) for c in winners)
    distinct_sources = sorted({c.source for c in winners})
    conf = base
    factors = {"base": round(base, 3)}
    reason = [f"base {base:.2f} (reliability x parser_conf, best of {distinct_sources})"]
    if len(distinct_sources) >= 2:
        conf += AGREEMENT_BONUS
        factors["agreement_bonus"] = AGREEMENT_BONUS
        reason.append(f"+{AGREEMENT_BONUS} agreement across {len(distinct_sources)} sources")
    if had_conflict:
        conf -= CONFLICT_PENALTY
        factors["conflict_penalty"] = -CONFLICT_PENALTY
        reason.append(f"-{CONFLICT_PENALTY} conflicting value(s) rejected")
    conf = round(max(0.0, min(CAP, conf)), 3)
    factors["final"] = conf
    return conf, factors, "; ".join(reason)


def overall(field_confidences: list[float]) -> float:
    vals = [c for c in field_confidences if c > 0]
    if not vals:
        return 0.0
    return round(sum(vals) / len(vals), 3)
