
# Multi-Source Candidate Data Transformer

Turns messy candidate inputs (a **recruiter CSV export** + one or more **resume PDFs**)
into one clean, canonical, deduplicated profile per candidate — with **provenance**
(where each value came from) and **confidence** (how much to trust it). Wrong-but-confident
is worse than honestly-empty, so unknown values become `null`, never invented.

## Demo video

▶ [`EightFold_Assignment_demovideo.mov`](./EightFold_Assignment_demovideo.mov) — click to download 

https://github.com/user-attachments/assets/be83ece8-f7d6-416e-835c-b93456cd9e15



## Sources implemented
- **Structured:** Recruiter CSV export (`src/parsers/csv_parser.py`)
- **Unstructured:** Resume PDF (`src/parsers/resume_parser.py`, text via `pdfplumber`)

## Pipeline
```
read → parse → normalize → resolve identity → merge → confidence/provenance → project → validate
```
Each parser emits a flat list of **Claims** (the intermediate representation): one atomic
`{field, value, source, method, confidence}` statement. The merge engine resolves all
Claims into a single `CanonicalProfile`. A separate **projection** layer reshapes the
output per a runtime config, then validates it — the engine never changes. Issues found
along the way go into a separate **diagnostics report**, never into the candidate profile.

## Install
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run
```bash
# Default schema (full profile + provenance + confidence)
python main.py --csv inputs/candidate.csv --resume inputs/resume.pdf \
               --config config/default.json --out outputs/default.json

# Custom config (field subset, rename, E164 phone, canonical skills, no provenance)
python main.py --csv inputs/candidate.csv --resume inputs/resume.pdf \
               --config config/custom.json --out outputs/custom.json

# Emit the diagnostics report (dropped values, ambiguous matches, low-confidence merges)
python main.py --csv inputs/candidate.csv --resume inputs/resume.pdf \
               --out outputs/default.json --report outputs/diagnostics.json
```
Omit `--out` to print to stdout. `--resume` is repeatable. Any source may be omitted.
`--region` sets the fallback phone region (default `IN`); otherwise it's derived from the
candidate's location. The sample data is Indian (e.g. `+91` numbers, `Bengaluru, Karnataka`),
and US/UK inputs still normalize correctly. A malformed config file fails fast with a clear
error rather than silently using defaults.

## Runtime config (reshapes output only)
```json
{
  "fields": [
    { "path": "full_name", "type": "string", "required": true },
    { "path": "primary_email", "from": "emails[0]", "type": "string", "required": true },
    { "path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164" },
    { "path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical" }
  ],
  "include_confidence": true,
  "include_provenance": false,
  "on_missing": "null"
}
```
`from` supports dotted paths and list ops (`emails[0]`, `skills[].name`). `on_missing` is
`null` | `omit` | `error`. `provenance_detail` is `compact` (default, schema-compatible
`[{field,source,method}]`) or `full` (value-level: chosen value, confidence, reason,
factors, rejected competitors). If `fields` is absent, the full default schema is emitted.

## Identity resolution (scored, not equality)
Deciding two records are the same person is the riskiest step — a false merge corrupts a
profile. We score each pair from multiple signals (email 1.0, phone 0.9, name 0.4/0.2,
company/school 0.2, location 0.1) and act on thresholds: **≥0.90 auto-merge**,
**0.50–0.90 ambiguous** (not merged, reported for review), **<0.50 no merge**. Name alone
never reaches the merge threshold, so two "John Smith"s stay separate.

## Conflict resolution & confidence
- **Scalars:** highest `source_reliability × parser_confidence` wins; deterministic tie-break;
  rejected values kept as competitors in provenance.
- **Lists (emails/phones/skills):** union + dedupe on normalized value.
- **Experience:** matched on company **+ title similarity + date overlap/adjacency**, so two
  separate stints at the same employer stay separate and complementary fields merge
  (CSV gives company+title, resume gives dates).
- **Confidence** = base evidence + agreement bonus (sources agree) − conflict penalty
  (sources disagree); folded into each provenance entry with a written `reason`.
  `overall_confidence` = mean of populated field confidences.

## Diagnostics
A separate run report (`--report`) collects invalid phones, malformed CSV rows, failed
normalizations, ambiguous/low-confidence merges, and low-confidence profiles. It lives
outside the profile because it describes the *run*, not the *candidate*.

## Tests
```bash
python -m pytest -q
```
Covers normalization, merge/conflict, scored identity (incl. "never merge on name alone"),
date-aware experience merge, robustness (malformed CSV, corrupt/missing PDF, missing phone,
required-field errors), and a **golden-output test** that locks byte-for-byte determinism.

## Design decisions
- **Claims as the IR** make merge/provenance/confidence uniform and explainable.
- **Projection separated from the canonical record** keeps "what we know" vs "what this
  consumer wants" cleanly split and config-driven.
- **Pydantic** validates the canonical model; the projection layer validates the requested shape.
- **Blocking for scalable identity resolution** — candidates are bucketed by shared keys
  (email, phone, name, company, school) and only pairs within a bucket are scored, so the
  pipeline scales to many thousands of candidates instead of an O(n²) all-pairs comparison.
  The bucket keys are chosen so no real match is skipped (verified by the golden output).

## Assumptions
- The CSV has a header row; column names are matched loosely (case/spacing-insensitive aliases).
- Resumes are text-extractable PDFs, not scanned images (no OCR step).
- A shared email or phone is strong evidence of the same person; a shared name is not.
- When a phone number has no country code, the candidate's location implies the region;
  if location is unknown, it falls back to `--region` (default `IN`).
- The recruiter CSV is slightly more reliable than resume prose, so it wins close ties.

## Limitations / descoped
- Resume parsing is heuristic (regex + section segmentation), not ML-based; image-only PDFs
  need OCR (not included). LinkedIn/GitHub sources are out of scope for this submission.
- Country table and skill dictionary are small inline lookups; production would use
  `pycountry` and a managed skills ontology.
- Identity blocking has a worst case: if nearly all candidates share one bucket key (e.g. the
  same company), that bucket falls back to O(n²) comparisons — acceptable at this scale.

## Project layout
```
src/
  models.py            # Claim (IR) + CanonicalProfile (canonical record)
  readers.py           # safe file/PDF reading
  parsers/             # csv_parser.py, resume_parser.py
  normalize/           # phone, dates, country, skills, text + apply.py
  identity.py          # scored multi-signal identity matching
  merge.py             # conflict resolution + value-level provenance + canonical build
  confidence.py        # scoring + human-readable explanation
  diagnostics.py       # run-level report collector
  config.py            # runtime config loading
  projection.py        # projection + validation (provenance compact|full)
  pipeline.py          # orchestrator (returns PipelineResult: profiles + diagnostics)
main.py                # CLI
```
