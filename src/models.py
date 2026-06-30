"""
Data models for the pipeline.

Two layers:
  1. The Intermediate Representation (IR): a flat list of `Claim`s.
    - Every parser emits Claims and nothing else.
    - A Claim is one atomic statement: "source X says field Y has value Z, extracted by method M, with parser confidence C".
  2. The canonical record (`CanonicalProfile`): the single clean profile that the merge
     engine builds from all the Claims. This is what is validated and projected.
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# Relative source reliability. Structured recruiter data is trusted slightly more than parsed resumes.
SOURCE_RELIABILITY: dict[str, float] = {
    "recruiter_csv": 0.90,
    "resume_pdf": 0.75,
}


class Claim(BaseModel):
    """One atomic fact from one source. The unit of the IR."""

    field: str               # canonical field key, e.g. "full_name", "emails", "experience"
    value: Any               # scalar, or a dict for object fields (experience/education/location/links)
    source: str              # "recruiter_csv" | "resume_pdf"
    method: str              # how it was extracted, e.g. "csv_cell", "pdf_contact_regex"
    confidence: float = 0.5  # parser-level confidence that this extraction is correct (0..1)
    raw: Optional[str] = None  # the original text, kept for debugging/explainability


class SourceBlock(BaseModel):
    """All claims extracted for one apparent person from a single source document."""
    source: str
    claims: list[Claim] = Field(default_factory=list)


# Canonical internal record matching the assignment's output schema.
class Location(BaseModel):
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None  # ISO-3166 alpha-2


class Links(BaseModel):
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    other: list[str] = Field(default_factory=list)


class Skill(BaseModel):
    name: str
    confidence: float
    sources: list[str] = Field(default_factory=list)


class Experience(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    start: Optional[str] = None   # YYYY-MM
    end: Optional[str] = None     # YYYY-MM or "present"
    summary: Optional[str] = None


class Education(BaseModel):
    institution: Optional[str] = None
    degree: Optional[str] = None
    field: Optional[str] = None
    end_year: Optional[int] = None


class Competitor(BaseModel):
    """A value we saw but did NOT choose, kept so the decision is auditable."""

    value: Any
    source: str
    method: str
    score: float
    rejected_because: str


class ValueProvenance(BaseModel):
    """Rich, value-level provenance for one chosen value.
    Internal record of why a value is in the profile.
    """
    field: str               # canonical path, e.g. "full_name", "emails", "location.country"
    value: Any
    source: str              # winning source (or "merged" when several agreed)
    method: str
    confidence: float
    reason: str              # human-readable: why this value won + how confidence was built
    factors: dict = Field(default_factory=dict)   # {base, agreement_bonus, conflict_penalty, final}
    competitors: list[Competitor] = Field(default_factory=list)


class CanonicalProfile(BaseModel):
    candidate_id: str
    full_name: Optional[str] = None
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    location: Location = Field(default_factory=Location)
    links: Links = Field(default_factory=Links)
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: list[Skill] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    value_provenance: list[ValueProvenance] = Field(default_factory=list)
    overall_confidence: float = 0.0
