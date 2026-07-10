"""SafeCard scoring (FR-015, design §7, research R10).

Inputs are ONLY: integrity signals, human-confirmed tier coverage from the
approved transform, value-level coverage observed on this document, and the
exception rate. Field-name overlap appears NOWHERE in this module — it is
never a trust signal (Constitution V).

Verdicts are per document; the batch summary aggregates them. A blocked
document is quarantined without blocking healthy ones (clarify 2026-07-10).
"""

from __future__ import annotations

import json
from pathlib import Path

VERDICTS = ("pass", "warn", "block")


def tier_coverage(doc: dict, required_fields: list[str]) -> float:
    """Share of required fields carried by human-confirmed mechanisms (T0/T1).

    Constants, formulas and prompts are human-authored, hence T0-equivalent.
    In an approved transform this is 1.0 by construction (FR-007); it is still
    computed and reported, never assumed.
    """
    if not required_fields:
        return 1.0
    ok = 0
    routes = doc.get("routes", {})
    for field in required_fields:
        if field in routes:
            if routes[field].get("tier") in ("T0", "T1"):
                ok += 1
        elif (
            field in doc.get("constants", {})
            or field in doc.get("formulas", {})
            or any((p.get("target_field") or p["key"]) == field for p in doc.get("prompts", []))
        ):
            ok += 1
    return ok / len(required_fields)


def document_verdict(
    *,
    document: str,
    sha256: str,
    blocked_reason: str | None,
    blocked_kind: str | None,
    rows_converted: int,
    findings_total: int,
    exceptions: list[dict],
    tiers: float,
) -> dict:
    oov = sum(1 for e in exceptions if e["kind"] == "oov_value")
    lookups_failed = oov
    value_coverage = (
        1.0
        if findings_total == 0
        else max(0.0, 1.0 - lookups_failed / findings_total)
    )
    if blocked_reason:
        verdict = "block"
    elif exceptions:
        verdict = "warn"
    else:
        verdict = "pass"
    return {
        "document": document,
        "sha256": sha256,
        "verdict": verdict,
        "blocked_kind": blocked_kind or "",
        "reason": blocked_reason or "",
        "findings_total": findings_total,
        "rows_converted": rows_converted,
        "exception_count": len(exceptions),
        "value_coverage": round(value_coverage, 4),
        "tier_coverage": round(tiers, 4),
    }


def build_safecard(documents: list[dict]) -> dict:
    counts = {v: 0 for v in VERDICTS}
    for d in documents:
        counts[d["verdict"]] += 1
    blocked = [d["document"] for d in documents if d["verdict"] == "block"]
    return {
        "documents": documents,
        "batch": {
            "total": len(documents),
            "verdicts": counts,
            "blocked_documents": blocked,  # every blocked document listed (FR-016)
            "exceptions_total": sum(d["exception_count"] for d in documents),
        },
    }


def write_safecard(out_dir: Path, safecard: dict) -> Path:
    path = Path(out_dir) / "safecard.json"
    path.write_text(
        json.dumps(safecard, sort_keys=True, indent=1) + "\n", encoding="utf-8"
    )
    return path
