"""Link-level value-map staging (US3, FR-021).

Edits stage in the session's DRAFT value-map file — the exact path the CLI
starter writes (`session_{id}.valuemap.{name}.yaml`) and `rmu valuemap create`
consumes — so no registry version is created per save, and CLI review stays
interchangeable. A distinct "Register & pin" reads that file and appends a new
append-only ValueMap version via the shared registry.create_value_map, then
pins name@version on the route. Nothing here writes a registry row directly.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from rmu import store as blobstore


def staged_path(session_id: int, name: str) -> Path:
    return blobstore.drafts_dir() / f"session_{session_id}.valuemap.{name}.yaml"


def load_staged(session_id: int, name: str) -> list[dict]:
    path = staged_path(session_id, name)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("entries", [])


def stage_entries(session_id: int, name: str, entries: list[dict]) -> Path:
    """Write the staged value-map file (no registry write). Same format the
    CLI starter uses so `rmu valuemap create --file <this>` is equivalent."""
    path = staged_path(session_id, name)
    path.write_text(yaml.safe_dump({"entries": entries}, sort_keys=True),
                    encoding="utf-8")
    return path


def suggest_name(source_from: str, target_field: str) -> str:
    """A value-map name derived from the link (analyst-editable, FR-021)."""
    source_key = source_from.split(".")[-1] if source_from else "source"
    return f"{source_key}_to_{target_field}"


def entries_from_parallel(source_values: list[str], target_values: list[str],
                          provenances: list[str]) -> list[dict]:
    """Build entries from the form's parallel arrays, preserving order."""
    return [
        {"source_value": s, "target_value": t, "provenance": p}
        for s, t, p in zip(source_values, target_values, provenances, strict=True)
    ]
