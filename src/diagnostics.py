"""Diagnostics: a separate run report, NOT part of the candidate profile.

A diagnostic describes the run (a malformed row, a dropped phone, a weak merge).  
Entries are appended in pipeline order, so the report is deterministic for a given input.
"""

from __future__ import annotations


class Diagnostics:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def add(self, stage: str, code: str, message: str,
            severity: str = "warning", **context) -> None:
        entry = {"stage": stage, "code": code, "severity": severity, "message": message}
        if context:
            entry["context"] = {k: v for k, v in context.items() if v is not None}
        self.entries.append(entry)

    def warn(self, stage: str, code: str, message: str, **context) -> None:
        self.add(stage, code, message, "warning", **context)

    def info(self, stage: str, code: str, message: str, **context) -> None:
        self.add(stage, code, message, "info", **context)

    def report(self) -> dict:
        counts: dict[str, int] = {}
        for e in self.entries:
            counts[e["severity"]] = counts.get(e["severity"], 0) + 1
        return {"summary": counts, "entries": self.entries}
