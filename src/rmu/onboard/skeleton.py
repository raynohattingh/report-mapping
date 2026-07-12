"""Empty-analysis skeleton + diagnosis (FR-001b).

When a valid text PDF yields no detectable record structure, onboarding is
never a dead end: the analyst gets a diagnosis of what was searched vs found
plus a proposal that can be hand-filled in the normal review flow — manual
authoring through the standard lifecycle is the degradation floor (D3 spirit).
"""

from __future__ import annotations

SEARCHED = [
    "repeating record rows (aligned lines sharing a first-cell structure class)",
    "table header line above >=3 aligned data rows",
    "header 'Label: value' blocks on lead pages",
    "page anatomy (recurring header/footer furniture)",
    "per-record images correlated to row positions",
]


def is_structureless(document: dict) -> bool:
    """No record table detected -> the FR-001b path."""
    return not any(e["element_kind"] == "record_table" for e in document["elements"])


def attach_diagnosis(document: dict) -> dict:
    """Add the what-was-searched/what-was-found diagnosis to a structureless
    proposal document. The remaining elements (if any) stay reviewable."""
    kinds = sorted({e["element_kind"] for e in document["elements"]})
    found = [f"{sum(1 for e in document['elements'] if e['element_kind'] == k)}x {k}"
             for k in kinds]
    document["diagnosis"] = {
        "searched": SEARCHED,
        "found": found or ["nothing usable"],
        "notes": (
            "no record structure detected - this proposal is a skeleton: add "
            "elements by hand in the draft YAML (same review/approve flow), or "
            "abandon if the document is not a structured report"
        ),
    }
    return document
