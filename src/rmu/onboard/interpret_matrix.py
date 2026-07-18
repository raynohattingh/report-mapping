"""Optional AI structural interpretation of a reconstructed matrix (feature 005).

The interpreter reasons over pdfplumber's extracted grid (+ optional page image)
and proposes axis labels/structure BY INDEX. This stage only ANNOTATES axis
entries with `suggested_*` (provenance ai) — it never overwrites a heuristic
label, never emits coordinates, never confirms. Every referenced (row/col) index
must exist in the grid; anything else is dropped and counted (the 002 gate
pattern). Skipped entirely under --no-ai; a no-op when no model is available.
"""
from __future__ import annotations

from typing import Protocol


class AxisInterpreter(Protocol):
    def interpret(self, grid: list[list[str]], page_image_png: bytes | None) -> dict | None: ...


class StubAxisInterpreter:
    """Deterministic interpreter for tests — returns a canned payload."""

    def __init__(self, payload: dict):
        self._payload = payload

    def interpret(self, grid, page_image_png=None):  # noqa: ARG002
        return self._payload


def _grid_index(grid: list[list[str]]) -> tuple[set[int], set[int]]:
    rows = set(range(len(grid)))
    cols = set(range(max((len(r) for r in grid), default=0)))
    return rows, cols


def apply_interpretation(
    document: dict,
    grids: dict[int, list[list[str]]],
    interpreter: AxisInterpreter | None,
    images: dict[int, bytes] | None = None,
) -> tuple[dict, dict[str, int]]:
    """Annotate `document`'s row_axis/col_axis entries with `suggested_*` hints.

    Mutates `document` IN PLACE (annotates existing axis-entry dicts nested
    inside it) and also returns it — callers may use either the return value
    or the object they passed in; both refer to the same document. Every
    dropped candidate is counted in the returned dict, never silently
    absorbed: `unknown_index` for a `(row, col)` referent outside the
    extracted grid's bounds, `unmatched_axis_entry` for an in-bounds referent
    that names no existing axis entry (a valid index, wrong/stale binding).
    """
    dropped = {"unknown_index": 0, "unmatched_axis_entry": 0}
    if interpreter is None:
        return document, dropped

    axes = {e["element_kind"]: e for e in document["elements"]
            if e["element_kind"] in ("row_axis", "col_axis")}
    for page_no, grid in grids.items():
        img = (images or {}).get(page_no)
        proposal = interpreter.interpret(grid, img)
        if not proposal:
            continue
        valid_rows, valid_cols = _grid_index(grid)

        for entry in proposal.get("row_axis", {}).get("entries", []):
            if entry.get("row") not in valid_rows:
                dropped["unknown_index"] += 1
                continue
            if not _annotate(axes.get("row_axis"), "row", entry.get("row"), entry):
                dropped["unmatched_axis_entry"] += 1

        for entry in proposal.get("col_axis", {}).get("entries", []):
            if entry.get("col") not in valid_cols:
                dropped["unknown_index"] += 1
                continue
            if not _annotate(axes.get("col_axis"), "col", entry.get("col"), entry):
                dropped["unmatched_axis_entry"] += 1
    return document, dropped


def _annotate(
    axis_element: dict | None, key: str, index: int | None, proposed: dict
) -> bool:
    """Annotate the axis entry at `index` with `proposed`'s suggestion fields.

    Returns True if a matching entry was found and annotated, False otherwise
    (no axis element of this kind, or no entry with `key == index`) — the
    caller counts False as a dropped `unmatched_axis_entry`.
    """
    if axis_element is None:
        return False
    for target in axis_element["payload"]["entries"]:
        if target.get(key) == index:
            if proposed.get("label"):
                target["suggested_label"] = proposed["label"]
            if proposed.get("number") is not None:
                target["suggested_number"] = proposed["number"]
            if proposed.get("confidence") is not None:
                target["suggested_confidence"] = proposed["confidence"]
            axis_element.setdefault("evidence", {})["ai_assist"] = True
            return True
    return False
