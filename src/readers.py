"""File readers: pull raw text off disk. Any failure (missing, unreadable, corrupt)
returns None instead of raising, so the pipeline can degrade gracefully."""

from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger("pipeline.readers")


def read_text(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    if not os.path.exists(path):
        log.warning("file not found: %s", path)
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError as e:
        log.warning("could not read %s: %s", path, e)
        return None


def read_pdf_text(path: Optional[str]) -> Optional[str]:
    """Extract text from a PDF."""
    if not path:
        return None
    if not os.path.exists(path):
        log.warning("file not found: %s", path)
        return None
    try:
        import pdfplumber
    except ImportError:
        log.error("pdfplumber not installed; cannot read PDFs")
        return None
    try:
        chunks = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                chunks.append(page.extract_text() or "")
        text = "\n".join(chunks).strip()
        return text or None
    except Exception as e:  # pdfplumber raises a variety of errors on bad files
        log.warning("could not parse PDF %s: %s", path, e)
        return None
