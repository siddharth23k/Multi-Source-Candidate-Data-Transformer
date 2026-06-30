"""Skill canonicalization: map many spellings to one canonical name."""

from __future__ import annotations

import re
from typing import Optional

# alias (lowercased) -> canonical display name.
_CANON = {
    "js": "JavaScript", "javascript": "JavaScript", "node": "Node.js",
    "nodejs": "Node.js", "node.js": "Node.js",
    "ts": "TypeScript", "typescript": "TypeScript",
    "py": "Python", "python": "Python", "python3": "Python",
    "golang": "Go", "go": "Go",
    "c++": "C++", "cpp": "C++", "cplusplus": "C++",
    "c#": "C#", "csharp": "C#",
    "reactjs": "React", "react.js": "React", "react": "React",
    "postgres": "PostgreSQL", "postgresql": "PostgreSQL", "psql": "PostgreSQL",
    "k8s": "Kubernetes", "kubernetes": "Kubernetes",
    "ml": "Machine Learning", "machine learning": "Machine Learning",
    "aws": "AWS", "amazon web services": "AWS",
    "sql": "SQL", "rest": "REST", "rest api": "REST", "restful": "REST",
    "tf": "TensorFlow", "tensorflow": "TensorFlow", "pytorch": "PyTorch",
    "docker": "Docker", "git": "Git",
}


def canonical_skill(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    key = re.sub(r"\s+", " ", value.strip().lower())
    if not key:
        return None
    if key in _CANON:
        return _CANON[key]
    # Unknown skill: title-case it as a best-effort canonical name, but keep
    # acronyms (<=3 chars, no spaces) uppercased.
    if len(key) <= 3 and " " not in key:
        return key.upper()
    return key.title()
