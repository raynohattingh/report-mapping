"""Session-side profile-fingerprint similarity (FR-015, research R7).

Given a new document, suggest which registered source profiles it structurally
resembles — an onboarding aid for the analyst, ranked by embedding similarity
of structural signatures. This NEVER touches apply-time detection: it reads
registry rows and reuses detect's read-only leading-text helper, leaving
`rmu.detect.fingerprint` unmodified (Principle VI). Output is framed as
"resembles", never a match verdict (Principle V).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def profile_signature(profile_row) -> str:
    """A structural descriptor string for a registered profile."""
    fp = profile_row.fingerprint or {}
    parts = list(fp.get("required_text", []))
    if fp.get("table_header_regex"):
        parts.append(str(fp["table_header_regex"]))
    parts += [profile_row.platform, profile_row.job_type, profile_row.export_kind]
    return " ".join(str(p) for p in parts if p)


def document_signature(pdf_path: Path) -> str:
    """Leading-page text of the document (reuses detect's read-only helper)."""
    from rmu.detect.fingerprint import _leading_text

    return _leading_text(Path(pdf_path))[:2000]


def suggest_profiles(pdf_path: Path, profiles: list, backend) -> list[dict]:
    """Rank profiles by structural resemblance to the document. Descending score,
    deterministic lexical tie-break on the profile key."""
    if not profiles:
        return []
    doc_vec = np.asarray(backend.embed([document_signature(pdf_path)])[0])
    doc_vec = doc_vec / (np.linalg.norm(doc_vec) or 1.0)
    prof_vecs = np.asarray(backend.embed([profile_signature(p) for p in profiles]))
    prof_vecs = prof_vecs / np.clip(
        np.linalg.norm(prof_vecs, axis=1, keepdims=True), 1e-12, None
    )
    scores = prof_vecs @ doc_vec
    keys = [f"{p.key}@{p.structural_version}" for p in profiles]
    order = sorted(range(len(profiles)), key=lambda i: (-float(scores[i]), keys[i]))
    return [{"profile": keys[i], "score": round(float(scores[i]), 4)} for i in order]
