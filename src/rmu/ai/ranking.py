"""Tier-1 candidate ranking (FR-005/012, research R5).

For each source field, rank the target schema fields by embedding cosine
similarity and return a short shortlist. These are *candidates* an analyst
chooses from — never a decision, never dressed up as confidence (Principle V):
scores accompany a "resembles" framing in the UI, and the true match only needs
to land in the top few (SC-002).
"""

from __future__ import annotations

import numpy as np

DEFAULT_TOP_K = 5


def humanize(name: str) -> str:
    """Field/path token to a natural phrase: 'finding.source_page' -> 'source page'."""
    tail = name.split(".")[-1]
    return tail.replace("_", " ").strip()


def descriptor_for_source(path: str, sample: str | None = None) -> str:
    text = humanize(path)
    if sample:
        text = f"{text}: {sample}"
    return text


def descriptor_for_target(name: str, label: str | None = None) -> str:
    return humanize(label) if label else humanize(name)


def _unit(rows: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(rows, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return rows / norms


def rank_candidates(
    source_fields: dict[str, str],
    target_fields: dict[str, str],
    backend,
    top_k: int = DEFAULT_TOP_K,
) -> dict[str, list[dict]]:
    """Map each source field to a ranked shortlist of target fields.

    `source_fields`/`target_fields` map a stable key to its descriptor text.
    Returns `{source_key: [{"target_field", "score"}, ...]}`, ordered by
    descending similarity with a deterministic lexical tie-break (FR-012).
    """
    if not source_fields or not target_fields:
        return {skey: [] for skey in source_fields}

    target_names = sorted(target_fields)
    tvecs = _unit(np.asarray(backend.embed([target_fields[t] for t in target_names])))
    svecs = _unit(np.asarray(backend.embed([source_fields[s] for s in sorted(source_fields)])))

    k = min(top_k, len(target_names))
    result: dict[str, list[dict]] = {}
    for row, skey in zip(svecs, sorted(source_fields), strict=True):
        sims = tvecs @ row
        order = sorted(
            range(len(target_names)),
            key=lambda i: (-float(sims[i]), target_names[i]),
        )
        result[skey] = [
            {"target_field": target_names[i], "score": round(float(sims[i]), 4)}
            for i in order[:k]
        ]
    return result
