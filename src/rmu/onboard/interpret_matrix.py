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


def apply_interpretation(document, grids, interpreter, images=None):
    dropped = {"unknown_index": 0}
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
            _annotate(axes.get("row_axis"), "row", entry.get("row"), entry)

        for entry in proposal.get("col_axis", {}).get("entries", []):
            if entry.get("col") not in valid_cols:
                dropped["unknown_index"] += 1
                continue
            _annotate(axes.get("col_axis"), "col", entry.get("col"), entry)
    return document, dropped


def _annotate(axis_element, key, index, proposed) -> None:
    if axis_element is None:
        return
    for target in axis_element["payload"]["entries"]:
        if target.get(key) == index:
            if proposed.get("label"):
                target["suggested_label"] = proposed["label"]
            if proposed.get("number") is not None:
                target["suggested_number"] = proposed["number"]
            if proposed.get("confidence") is not None:
                target["suggested_confidence"] = proposed["confidence"]
            axis_element.setdefault("evidence", {})["ai_assist"] = True
            return
