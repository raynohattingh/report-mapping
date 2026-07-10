from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

#: How many leading pages detection scans for anchors.
SCAN_PAGES = 4


def _leading_text(pdf_path: Path) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages[:SCAN_PAGES])


def matches_fingerprint(pdf_path: Path, fingerprint: dict) -> bool:
    try:
        text = _leading_text(pdf_path)
    except Exception:
        return False  # unreadable/not a PDF -> not this profile
    if not all(anchor in text for anchor in fingerprint.get("required_text", [])):
        return False
    header_re = fingerprint.get("table_header_regex")
    if header_re:
        pattern = re.compile(header_re, re.MULTILINE)
        if not pattern.search(text):
            return False
    return True


def detect_profile(pdf_path: Path, profiles: list) -> object | None:
    """Return the first matching profile row, or None (unknown -> quarantine)."""
    for profile in profiles:
        if profile.status == "active" and matches_fingerprint(pdf_path, profile.fingerprint):
            return profile
    return None
