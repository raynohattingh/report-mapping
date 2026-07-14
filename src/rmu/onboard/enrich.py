"""Optional local-AI enrichment of a draft proposal (FR-020, research R4).

Naming/label hints ONLY: the LLM never proposes structure, never confirms
anything, and never overwrites a heuristic value — it adds `suggested_name`
hints the analyst sees during review. Skipped entirely under --no-ai; degrades
to a no-op when no local model is available (002 tier semantics, D8). Page
sampling keeps enrichment inside the SC-009 budget on large documents.
"""

from __future__ import annotations

import json

#: at most this many pages of context go to the local model (SC-009)
MAX_SAMPLED_PAGES = 6

_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "name": {"type": "string"}},
                "required": ["id", "name"],
            },
        }
    },
    "required": ["suggestions"],
}


def sample_pages(page_texts: list[str]) -> list[int]:
    """Representative 1-based page numbers: first, last, and the densest pages
    in between, capped at MAX_SAMPLED_PAGES (research R4)."""
    n = len(page_texts)
    if n <= MAX_SAMPLED_PAGES:
        return list(range(1, n + 1))
    ranked = sorted(range(1, n - 1), key=lambda i: len(page_texts[i]), reverse=True)
    middle = sorted(ranked[: MAX_SAMPLED_PAGES - 2])
    return [1] + [i + 1 for i in middle] + [n]


def enrich_document(document: dict, page_texts: list[str], llm=None) -> dict:
    """Add naming hints to nameable elements. `llm` is a LocalLLM-shaped object
    (available() -> bool, complete_json(prompt, format_schema=...) -> str|None);
    None or unavailable => untouched document, no ai_assist block."""
    if llm is None or not llm.available():
        return document

    nameable = [
        e
        for e in document["elements"]
        if e["element_kind"] in ("header_field", "record_column")
    ]
    if not nameable:
        return document

    pages = sample_pages(page_texts)
    context = "\n\n".join(f"[page {p}]\n{page_texts[p - 1][:1500]}" for p in pages)
    listing = "\n".join(
        f"- id={e['id']} kind={e['element_kind']} current_name={e['payload'].get('name')!r}"
        f" source_header={e['payload'].get('source_header') or e['payload'].get('labels')}"
        for e in nameable
    )
    prompt = (
        "You are labelling fields extracted from a drone-inspection report.\n"
        "For each element below, suggest a concise snake_case field name that a "
        "data analyst would use. Do not invent elements; reply for the given ids "
        'only, as JSON {"suggestions": [{"id": ..., "name": ...}]}.\n\n'
        f"Document excerpts:\n{context}\n\nElements:\n{listing}"
    )
    raw = llm.complete_json(prompt, format_schema=_SCHEMA)
    if not raw:
        return document
    try:
        suggestions = {s["id"]: s["name"] for s in json.loads(raw)["suggestions"]}
    except (ValueError, KeyError, TypeError):
        return document  # malformed model output: hints dropped, never guessed in

    applied = []
    for e in nameable:
        name = suggestions.get(e["id"])
        if name and name != e["payload"].get("name"):
            e["payload"]["suggested_name"] = name  # hint only - analyst decides
            e["evidence"] = {**e.get("evidence", {}), "ai_hint": True}
            applied.append({"id": e["id"], "suggested_name": name})

    document["ai_assist"] = {
        "mode": "local",
        "sampled_pages": pages,
        "enrichments": applied,
    }
    return document
