"""Pipeline orchestrator. Wires the stages together:

  read -> parse -> normalize -> resolve identity -> merge -> project/validate

Every stage is defensive and reports issues to a Diagnostics report.
Returns a PipelineResult (profiles + diagnostics)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import readers
from .parsers import csv_parser, resume_parser
from .normalize.apply import normalize_claims
from . import identity, merge as merge_mod
from .projection import project
from .diagnostics import Diagnostics


@dataclass
class PipelineResult:
    profiles: list[dict] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)


def run(csv_path: Optional[str] = None,
        resume_paths: Optional[list[str]] = None,
        config: Optional[dict] = None,
        phone_region: str = "IN") -> PipelineResult:
    config = config or {}
    resume_paths = resume_paths or []
    diag = Diagnostics()

    # 1. READ + PARSE -> SourceBlocks (raw claims + identity hints)
    blocks = []
    blocks += csv_parser.parse(readers.read_text(csv_path), diag=diag)
    for rp in resume_paths:
        blocks += resume_parser.parse(readers.read_pdf_text(rp), diag=diag)

    if not blocks:
        diag.warn("pipeline", "no_source_data", "no usable source data found")
        return PipelineResult(profiles=[], diagnostics=diag.report())

    # 2. NORMALIZE every claim (region derived per-block from location if present)
    for b in blocks:
        region = _region_for(b, phone_region)
        b.claims = normalize_claims(b.claims, phone_region=region, diag=diag)

    # 3. IDENTITY RESOLUTION -> group blocks per person (scored matching)
    groups = identity.group(blocks, diag=diag)

    # 4. MERGE + 5. PROJECT/VALIDATE per candidate
    outputs = []
    for grp in groups:
        all_claims = [c for b in grp for c in b.claims]
        if not all_claims:
            continue
        profile = merge_mod.merge(all_claims)
        if profile.overall_confidence < 0.4:
            diag.warn("merge", "low_confidence_profile",
                      f"profile {profile.candidate_id} has low overall confidence "
                      f"({profile.overall_confidence}); review recommended",
                      candidate_id=profile.candidate_id)
        outputs.append(project(profile, config))

    return PipelineResult(profiles=outputs, diagnostics=diag.report())


# Derive the phone region from the candidate's own location
def _region_for(block, fallback: str) -> str:
    from .normalize.country import parse_location
    for c in block.claims:
        if c.field == "location" and isinstance(c.value, str):
            country = parse_location(c.value).get("country")
            if country:
                return country
    return fallback
