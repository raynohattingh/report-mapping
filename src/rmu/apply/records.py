"""Strict per-document apply: NormalizedRecords + Transform -> target rows +
exceptions (FR-011/FR-012). Pure and deterministic; no imports beyond the
engine primitives (guarded by tests/invariants/test_no_ai_in_apply.py)."""

from __future__ import annotations

from rmu.apply.engine import resolve_record


def apply_records(
    doc: dict,
    normalized: dict,
    prompt_answers: dict[str, str],
    value_maps: dict[tuple[str, int], list[dict]],
    columns: list[str],
) -> tuple[list[dict], list[dict]]:
    """One output row per healthy finding; problems become exception dicts.

    A record that cannot be fully converted produces NO row (never a guessed
    or partial conversion) and one exception per failure, each carrying the
    record reference, failing detail, reason and suggested resolution.
    """
    rows: list[dict] = []
    exceptions: list[dict] = []
    header = normalized["header"]

    for finding in normalized["findings"]:
        ref = finding.get("id") or "?"
        if "parse_error" in finding:
            exceptions.append({
                "record_ref": ref,
                "kind": "record_parse",
                "detail": {
                    "field": "",
                    "value": "",
                    "reason": finding["parse_error"],
                    "suggestion": "inspect the source row; extraction could not read it",
                },
            })
            continue
        context = {"header": header, "finding": finding, "prompt": prompt_answers}
        values, problems = resolve_record(columns, doc, context, value_maps, strict=True)
        if problems:
            for p in problems:
                exceptions.append({
                    "record_ref": ref,
                    "kind": p["kind"],
                    "detail": {
                        "field": p["field"],
                        "value": str(finding.get(_source_key(doc, p["field"]), "")),
                        "reason": p["reason"],
                        "suggestion": p["suggestion"],
                    },
                })
            continue  # no partial/guessed rows (FR-012)
        rows.append(values)
    return rows, exceptions


def _source_key(doc: dict, target_field: str) -> str:
    route = doc.get("routes", {}).get(target_field)
    if route:
        return route["from"].partition(".")[2]
    return ""
