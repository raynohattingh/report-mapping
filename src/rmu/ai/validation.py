"""Strict proposal gate (FR-008, research R4).

Two stages, both untrusting of the model:
  1. shape — each item validated against proposal.schema.json (per-item, so one
     bad object never sinks the batch);
  2. referents — from_path must exist in the exemplar's source inventory,
     target_field must be a real template field, and value-map source values
     must have actually been observed.
Anything failing is dropped and counted by reason ({schema, unknown_field,
unknown_value}); nothing malformed is ever surfaced as a trusted proposal.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from rmu.mapping.providers import Proposal

_SCHEMA_PATH = Path(__file__).parent.parent / "mapping" / "schemas" / "proposal.schema.json"
_item_schema = json.loads(_SCHEMA_PATH.read_text())["items"]
_item_validator = jsonschema.Draft202012Validator(_item_schema)


def _from_path_exists(from_path: str, source_inventory: dict) -> bool:
    scope, _, key = from_path.partition(".")
    return key in (source_inventory.get(scope) or {})


# Local models under Ollama's `format:"json"` reliably return a top-level OBJECT,
# not the array we ask for (observed with qwen3:4b). Coerce common shapes to a
# list so a correct-but-object response is not thrown away wholesale. Structured
# outputs (a schema passed as `format`) make the wrapper predictable; this is the
# defensive backstop for whatever a model actually emits.
_WRAPPER_KEYS = ("proposals", "mappings", "routes", "items", "results")


def _coerce_items(parsed: object) -> list | None:
    """Normalize model output to a list of proposal objects, or None if unusable."""
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for key in _WRAPPER_KEYS:
            if isinstance(parsed.get(key), list):
                return parsed[key]
        for value in parsed.values():  # any single array value
            if isinstance(value, list):
                return value
        if "target_field" in parsed and "from_path" in parsed:  # a lone proposal
            return [parsed]
    return None


def gate_proposals(
    raw_json: str,
    *,
    source_inventory: dict,
    target_fields: set[str],
    observed_values: dict[str, set[str]],
) -> tuple[list[Proposal], dict[str, int]]:
    """Return (surviving proposals, dropped-by-reason counts)."""
    dropped = {"schema": 0, "unknown_field": 0, "unknown_value": 0}

    try:
        parsed = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        dropped["schema"] += 1
        return [], dropped
    items = _coerce_items(parsed)
    if items is None:
        dropped["schema"] += 1
        return [], dropped

    proposals: list[Proposal] = []
    for item in items:
        if not isinstance(item, dict) or list(_item_validator.iter_errors(item)):
            dropped["schema"] += 1
            continue
        if item["target_field"] not in target_fields or not _from_path_exists(
            item["from_path"], source_inventory
        ):
            dropped["unknown_field"] += 1
            continue

        entries = []
        for entry in item.get("suggested_entries", []):
            observed = observed_values.get(item["from_path"], set())
            if str(entry["source_value"]) not in observed:
                dropped["unknown_value"] += 1
                continue
            entries.append({
                "source_value": entry["source_value"],
                "target_value": entry["target_value"],
                "provenance": "ai-accepted",
                "note": entry.get("note", "AI suggestion pending review"),
            })

        proposals.append(Proposal(
            target_field=item["target_field"],
            from_path=item["from_path"],
            rationale=item["rationale"],
            value_map_name=item.get("value_map_name"),
            suggested_entries=entries,
        ))
    return proposals, dropped
