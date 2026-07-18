# Matrix-aware Target Onboarding — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconstruct a grid target's two axes (criteria rows, tower columns) so every cell derives a meaningful `(row_id, col_id)` field name, with an optional AI `interpret` stage that understands the form's structure over pdfplumber's extracted grid — turning "373 regions named `10_10`" into ~25 reviewable axis decisions.

**Architecture:** Deterministic axis reconstruction runs always (the `--no-ai` floor). A separate, optional `interpret_matrix` stage adds `suggested_*` label/structure hints to the axis elements, validated by a referent-resolution gate that references pdfplumber cells by index only (never coordinates). Cells inherit names from the two axes. Apply/verify are unchanged: a cell is still an `overlay_region` (bbox + `target_field`).

**Tech Stack:** Python 3.12, uv, pytest, ruff, pdfplumber, reportlab (test fixtures), PyYAML/jsonschema, Ollama (vision) via stdlib urllib.

## Global Constraints

- No AI at apply time, ever (Constitution II) — AI is onboarding-only, as reviewed proposals. `interpret` only annotates axis elements; it never writes geometry, never confirms, never overwrites a heuristic value.
- Templates/recipes are data, not code (Constitution IV) — the matrix representation lives in the proposal document and `TargetTemplate.required_schema`, never in pipeline logic.
- Registries are append-only, versioned (Constitution III) — re-onboarding registers a new template version; nothing is mutated.
- Local-first, `--no-ai` must always work; external assist is per-client consent-gated (Constitution VII / rule 7). Build/test on the Eskom holdout (blank template) + synthetic fixtures only; no real client data to any external API.
- Determinism: same inputs → byte-identical apply output (timestamps excepted). The deterministic axis pass must be pure; AI output is gated + human-reviewed before it can affect a registered artifact.
- Cite `A#`/`D#`/`FR-###` in comments/commits where a decision is relied on. Log any new assumption in `ASSUMPTIONS.md` BEFORE use.
- Zero network in the test suite — the AI interpreter is exercised only through a deterministic `StubAxisInterpreter`.

---

### Task 1: Synthetic matrix fixture

Build a small, deterministic grid PDF that is a genuine criteria×tower matrix, so every later task tests against known ground truth (mirrors how `tests/fixtures/onboarding/target_grid.pdf` was seeded).

**Files:**
- Create: `tests/fixtures/onboarding/build_matrix_target.py`
- Create (generated, committed): `tests/fixtures/onboarding/matrix_target.pdf`
- Test: `tests/unit/test_matrix_fixture.py`

**Interfaces:**
- Produces: `matrix_target.pdf` — 1 page, A4 landscape. Header row = `["No", "Criterion", "T1", "T2", "T3"]`; content rows `("4.1","Broken stay wire"), ("4.2","Corrosion"), ("4.3","Bird streamer")`; the 3 tower columns are blank fillable cells. Drawn as grid LINES (not filled rects), matching the hairline-grid case.

- [ ] **Step 1: Write the fixture builder**

```python
# tests/fixtures/onboarding/build_matrix_target.py
"""Seed a deterministic criteria x tower matrix PDF (lines-only grid, blank
answer cells) — the synthetic stand-in for the Eskom Annexure holdout."""
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

OUT = Path(__file__).with_name("matrix_target.pdf")
HEADER = ["No", "Criterion", "T1", "T2", "T3"]
ROWS = [("4.1", "Broken stay wire"), ("4.2", "Corrosion"), ("4.3", "Bird streamer")]
COL_X = [40, 90, 300, 380, 460, 540]   # 5 columns -> 6 boundaries
ROW_Y = [500, 460, 420, 380]           # header + 3 rows -> 4 boundaries (top→down)


def build(out: Path = OUT) -> Path:
    c = canvas.Canvas(str(out), pagesize=landscape(A4))
    for x in COL_X:                                  # vertical grid lines
        c.line(x, ROW_Y[-1], x, ROW_Y[0])
    for y in ROW_Y:                                  # horizontal grid lines
        c.line(COL_X[0], y, COL_X[-1], y)
    for j, label in enumerate(HEADER):               # header text
        c.drawString(COL_X[j] + 3, ROW_Y[0] + 6, label)
    for i, (num, crit) in enumerate(ROWS):           # number + criterion text
        y = ROW_Y[0] - (i + 1) * 40 + 6
        c.drawString(COL_X[0] + 3, y, num)
        c.drawString(COL_X[1] + 3, y, crit)
    # tower columns (j = 2,3,4) left BLANK — the fillable answer cells
    c.showPage()
    c.save()
    return out


if __name__ == "__main__":
    print(build())
```

- [ ] **Step 2: Generate the fixture and write a guard test**

Run: `uv run python tests/fixtures/onboarding/build_matrix_target.py`
Expected: prints the path; `matrix_target.pdf` exists.

```python
# tests/unit/test_matrix_fixture.py
import pdfplumber
from pathlib import Path

FIXTURE = Path("tests/fixtures/onboarding/matrix_target.pdf")

def test_matrix_fixture_has_a_reconstructable_grid():
    assert FIXTURE.exists()
    with pdfplumber.open(FIXTURE) as pdf:
        tables = pdf.pages[0].find_tables()
    assert tables, "fixture must yield at least one table"
    grid = tables[0].extract()
    assert grid[0][:2] == ["No", "Criterion"]
    assert any("Corrosion" in (cell or "") for row in grid for cell in row)
```

- [ ] **Step 3: Run the test**

Run: `uv run pytest tests/unit/test_matrix_fixture.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/onboarding/build_matrix_target.py tests/fixtures/onboarding/matrix_target.pdf tests/unit/test_matrix_fixture.py
git commit -m "test(005): synthetic criteria x tower matrix fixture"
```

---

### Task 2: Deterministic axis reconstruction

Turn the extracted grid into `row_axis` + `col_axis` elements plus cell regions referencing `(row_id, col_id)`. This is the always-on floor; no AI.

**Files:**
- Create: `src/rmu/onboard/matrix.py`
- Test: `tests/unit/test_matrix_reconstruct.py`

**Interfaces:**
- Consumes: pdfplumber `find_tables()` output (from Task 1's fixture).
- Produces:
  - `reconstruct_matrix(pdf_path: Path) -> list[dict] | None` — returns axis + cell elements, or `None` when no reconstructable grid (caller keeps the old flat path).
  - Element kinds and payloads (element helper reused from `analyze_target._element`):
    - `row_axis` payload: `{"number_column": int|None, "text_column": int, "header_rows": list[int], "entries": [{"row": int, "id": str, "number": str|None, "label": str}]}`
    - `col_axis` payload: `{"entries": [{"col": int, "id": str, "label": str}]}`
    - cell `overlay_region` payload: `{"row_id": str, "col_id": str, "target_field": str, "kind": "text", "page": int, "bbox": [x0,y0,x1,y1]}`
  - `derive_field(row_id: str, col_id: str) -> str` returns `f"{row_id}__{col_id}"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_matrix_reconstruct.py
from pathlib import Path
from rmu.onboard.matrix import reconstruct_matrix, derive_field

FIXTURE = Path("tests/fixtures/onboarding/matrix_target.pdf")

def _by_kind(elements, kind):
    return [e for e in elements if e["element_kind"] == kind]

def test_reconstruct_builds_two_axes_and_cells():
    elements = reconstruct_matrix(FIXTURE)
    assert elements is not None
    row_axis = _by_kind(elements, "row_axis")[0]["payload"]
    col_axis = _by_kind(elements, "col_axis")[0]["payload"]
    # 3 criteria rows, 3 tower columns
    assert len(row_axis["entries"]) == 3
    assert len(col_axis["entries"]) == 3
    # number + text columns detected and paired
    assert row_axis["number_column"] == 0 and row_axis["text_column"] == 1
    # cells = 3 criteria x 3 towers = 9, each referencing both axes
    cells = _by_kind(elements, "overlay_region")
    assert len(cells) == 9
    row_ids = {e["payload"]["id"] for e in [_by_kind(elements, "row_axis")[0]]} or set()
    sample = cells[0]["payload"]
    assert sample["target_field"] == derive_field(sample["row_id"], sample["col_id"])
    assert sample["bbox"] and sample["page"] == 1

def test_reconstruct_returns_none_without_a_grid(tmp_path):
    from reportlab.pdfgen import canvas
    p = tmp_path / "blank.pdf"
    c = canvas.Canvas(str(p)); c.drawString(72, 720, "no grid here"); c.showPage(); c.save()
    assert reconstruct_matrix(p) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_matrix_reconstruct.py -v`
Expected: FAIL with `ModuleNotFoundError: rmu.onboard.matrix`

- [ ] **Step 3: Implement `matrix.py`**

```python
# src/rmu/onboard/matrix.py
"""Deterministic axis reconstruction for grid targets (feature 005).

pdfplumber's find_tables already yields cell text + exact bbox + (i,j). We keep
that geometry verbatim and add SEMANTIC structure: identify the tower header
band (top rows) and the criterion label band (left columns, number+text), emit
row_axis / col_axis elements, and make every blank answer cell reference both by
(row_id, col_id). No AI here — this is the --no-ai floor. Names are best-effort;
the interpret stage (interpret_matrix.py) and human review improve them.
"""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from rmu.onboard.analyze_target import _element, _slug

GRID_MIN_CELL_W = 12.0
GRID_MIN_CELL_H = 8.0
_NUMBERISH = re.compile(r"^\s*\d+(\.\d+)*\s*$")


def derive_field(row_id: str, col_id: str) -> str:
    return f"{row_id}__{col_id}"


def _text(grid, i, j) -> str:
    try:
        return " ".join((grid[i][j] or "").split())
    except (IndexError, TypeError):
        return ""


def _detect_bands(grid) -> tuple[list[int], int | None, int]:
    """(header_rows, number_column, text_column). Header band = leading rows
    whose left cells are non-numeric labels; number column = a left column whose
    data cells are numeric; text column = the next labelled left column."""
    ncols = max((len(r) for r in grid), default=0)
    # number column: first column that is numeric in most content rows
    number_column = None
    text_column = 0
    for j in range(min(ncols, 3)):
        vals = [_text(grid, i, j) for i in range(1, len(grid))]
        nonempty = [v for v in vals if v]
        if nonempty and sum(bool(_NUMBERISH.match(v)) for v in nonempty) >= max(1, len(nonempty) // 2):
            number_column = j
            text_column = j + 1
            break
    header_rows = [0]  # single header row for the deterministic floor
    return header_rows, number_column, text_column


def reconstruct_matrix(pdf_path: Path) -> list[dict] | None:
    elements: list[dict] = []
    found_grid = False
    used: dict[str, int] = {}

    def uid(base: str) -> str:
        base = base or "x"
        used[base] = used.get(base, 0) + 1
        return base if used[base] == 1 else f"{base}_{used[base]}"

    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            height = float(page.height)
            for table in page.find_tables():
                grid = table.extract()
                if not grid or len(grid) < 2 or max(len(r) for r in grid) < 3:
                    continue
                found_grid = True
                header_rows, number_col, text_col = _detect_bands(grid)
                label_cols = {c for c in (number_col, text_col) if c is not None}

                # row axis (criteria)
                row_entries, row_id_by_i = [], {}
                for i in range(len(grid)):
                    if i in header_rows:
                        continue
                    number = _text(grid, i, number_col) if number_col is not None else None
                    label = _text(grid, i, text_col) or number or f"row_{i}"
                    rid = uid(_slug(label) or f"row_{i}")
                    row_id_by_i[i] = rid
                    row_entries.append({"row": i, "id": rid,
                                        "number": number or None, "label": label[:80]})

                # col axis (towers)
                col_entries, col_id_by_j = [], {}
                ncols = max(len(r) for r in grid)
                for j in range(ncols):
                    if j in label_cols:
                        continue
                    label = _text(grid, header_rows[0], j) or f"col_{j}"
                    cid = uid(_slug(label) or f"col_{j}")
                    col_id_by_j[j] = cid
                    col_entries.append({"col": j, "id": cid, "label": label[:60]})

                elements.append(_element(
                    f"rowaxis-p{page_no}", "row_axis", 0.6,
                    {"pages": [page_no], "source": "heuristic"},
                    {"number_column": number_col, "text_column": text_col,
                     "header_rows": header_rows, "entries": row_entries}))
                elements.append(_element(
                    f"colaxis-p{page_no}", "col_axis", 0.6,
                    {"pages": [page_no], "source": "heuristic"},
                    {"entries": col_entries}))

                # cells (blank answer slots at criterion x tower intersections)
                counter = 0
                for i, row in enumerate(table.rows):
                    for j, cell in enumerate(row.cells):
                        if cell is None or i not in row_id_by_i or j not in col_id_by_j:
                            continue
                        x0, top, x1, bottom = cell
                        if x1 - x0 < GRID_MIN_CELL_W or bottom - top < GRID_MIN_CELL_H:
                            continue
                        if _text(grid, i, j):
                            continue  # pre-printed, not fillable
                        rid, cid = row_id_by_i[i], col_id_by_j[j]
                        elements.append(_element(
                            f"cell-p{page_no}-{counter}", "overlay_region", 0.6,
                            {"pages": [page_no], "source": "heuristic",
                             "row": i, "col": j},
                            {"row_id": rid, "col_id": cid,
                             "target_field": derive_field(rid, cid), "kind": "text",
                             "page": page_no,
                             "bbox": [round(x0, 1), round(height - bottom, 1),
                                      round(x1, 1), round(height - top, 1)]}))
                        counter += 1
    return elements if found_grid else None
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/unit/test_matrix_reconstruct.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/rmu/onboard/matrix.py tests/unit/test_matrix_reconstruct.py
git commit -m "feat(005): deterministic criteria x tower axis reconstruction"
```

---

### Task 3: Wire the matrix path into `analyze_target`

Make grid targets use the matrix reconstruction instead of flat `_grid_region_elements`, preserving the old path where no grid is found.

**Files:**
- Modify: `src/rmu/onboard/analyze_target.py` (the `_fixed_layout_elements` fallback branch around line 162-164)
- Test: `tests/unit/test_analyze_target_matrix.py`

**Interfaces:**
- Consumes: `reconstruct_matrix` (Task 2).
- Produces: `analyze(matrix_target.pdf, kind="fixed_layout")` returns a document whose `elements` include exactly one `row_axis`, one `col_axis`, and 9 `overlay_region` cells, plus the existing `cardinality` element.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_analyze_target_matrix.py
from pathlib import Path
from rmu.onboard.analyze_target import analyze

FIXTURE = Path("tests/fixtures/onboarding/matrix_target.pdf")

def test_analyze_uses_matrix_path_for_grid_targets():
    doc = analyze(FIXTURE, kind="fixed_layout")
    kinds = [e["element_kind"] for e in doc["elements"]]
    assert kinds.count("row_axis") == 1
    assert kinds.count("col_axis") == 1
    assert kinds.count("overlay_region") == 9
    # every cell derives its name from the two axes
    cells = [e for e in doc["elements"] if e["element_kind"] == "overlay_region"]
    assert all("__" in e["payload"]["target_field"] for e in cells)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_analyze_target_matrix.py -v`
Expected: FAIL (currently emits flat `_grid_region_elements` with no `row_axis`)

- [ ] **Step 3: Wire the matrix path**

In `src/rmu/onboard/analyze_target.py`, at the top add:
```python
from rmu.onboard.matrix import reconstruct_matrix
```
Replace the grid fallback (the `return _grid_region_elements(pdf_path)` call inside `_fixed_layout_elements`) with:
```python
        # Grid form: prefer 2-D axis reconstruction (feature 005); fall back to
        # the flat per-cell path only if no reconstructable grid is present.
        matrix = reconstruct_matrix(pdf_path)
        if matrix is not None:
            return matrix
        return _grid_region_elements(pdf_path)
```

- [ ] **Step 4: Run the test + the existing onboarding suite**

Run: `uv run pytest tests/unit/test_analyze_target_matrix.py tests/unit -k "target or onboard" -v`
Expected: PASS (new test passes; existing target tests still green — `target_grid.pdf` should now also reconstruct as a matrix, so update any assertion there that counted flat regions).

- [ ] **Step 5: Commit**

```bash
git add src/rmu/onboard/analyze_target.py tests/unit/test_analyze_target_matrix.py
git commit -m "feat(005): analyze_target prefers matrix reconstruction for grid forms"
```

---

### Task 4: The `interpret_matrix` gate (Stub interpreter)

Add the AI-suggestion stage: annotate axis elements with `suggested_*` from an interpreter, dropping any index reference not present in the grid. Prove it with a deterministic stub — no network.

**Files:**
- Create: `src/rmu/onboard/interpret_matrix.py`
- Test: `tests/unit/test_interpret_matrix.py`

**Interfaces:**
- Consumes: the document from Task 3; a grid (`list[list[str]]`) per page.
- Produces:
  - `AxisInterpreter` protocol: `interpret(grid: list[list[str]], page_image_png: bytes | None) -> dict | None` returning the index-referenced JSON from the design (`row_axis`/`col_axis`/`notes`), or `None` when unavailable.
  - `apply_interpretation(document: dict, grids: dict[int, list[list[str]]], interpreter: AxisInterpreter, images: dict[int, bytes] | None = None) -> tuple[dict, dict]` — returns `(document, dropped_counts)`. Adds `suggested_label`/`suggested_number` to axis entries whose `(row/col)` index exists; increments `dropped["unknown_index"]` otherwise. Never overwrites existing labels; sets `evidence.ai_assist` block. No-op (returns doc unchanged, zero drops) when `interpreter is None` or `interpret()` returns `None`.
  - `StubAxisInterpreter(payload: dict)` for tests.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_interpret_matrix.py
from rmu.onboard.interpret_matrix import apply_interpretation, StubAxisInterpreter

def _doc():
    return {"elements": [
        {"element_kind": "row_axis", "payload": {"number_column": 0, "text_column": 1,
            "header_rows": [0], "entries": [{"row": 1, "id": "r1", "number": None, "label": "row_1"}]}},
        {"element_kind": "col_axis", "payload": {"entries": [{"col": 2, "id": "c2", "label": "col_2"}]}},
    ]}

GRID = {1: [["No", "Criterion", "T1"], ["4.2", "", ""]]}

def test_interpretation_annotates_valid_indices():
    stub = StubAxisInterpreter({
        "row_axis": {"entries": [{"row": 1, "number": "4.2", "label": "Corrosion", "confidence": 0.9}]},
        "col_axis": {"entries": [{"col": 2, "label": "Tower 100", "confidence": 0.8}]},
    })
    doc, dropped = apply_interpretation(_doc(), GRID, stub)
    row = doc["elements"][0]["payload"]["entries"][0]
    col = doc["elements"][1]["payload"]["entries"][0]
    assert row["suggested_label"] == "Corrosion" and row["suggested_number"] == "4.2"
    assert col["suggested_label"] == "Tower 100"
    assert row["label"] == "row_1"  # original NOT overwritten (suggestion only)
    assert dropped["unknown_index"] == 0

def test_interpretation_drops_unknown_indices():
    stub = StubAxisInterpreter({"row_axis": {"entries": [
        {"row": 99, "label": "Ghost", "confidence": 0.9}]}, "col_axis": {"entries": []}})
    doc, dropped = apply_interpretation(_doc(), GRID, stub)
    assert dropped["unknown_index"] == 1
    assert "suggested_label" not in doc["elements"][0]["payload"]["entries"][0]

def test_no_interpreter_is_a_noop():
    doc, dropped = apply_interpretation(_doc(), GRID, None)
    assert dropped == {"unknown_index": 0}
    assert "suggested_label" not in doc["elements"][0]["payload"]["entries"][0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_interpret_matrix.py -v`
Expected: FAIL with `ModuleNotFoundError: rmu.onboard.interpret_matrix`

- [ ] **Step 3: Implement `interpret_matrix.py`**

```python
# src/rmu/onboard/interpret_matrix.py
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
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/unit/test_interpret_matrix.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/rmu/onboard/interpret_matrix.py tests/unit/test_interpret_matrix.py
git commit -m "feat(005): interpret_matrix gate — index-validated axis suggestions"
```

---

### Task 5: Local vision interpreter + assist-mode resolution + doctor

Provide a real `LocalVisionInterpreter` over Ollama (loopback, structured output), resolve it from the existing `none|local|external` assist mode (external consent-gated), and report health via `rmu ai doctor`. No network in tests — cover the resolver and the prompt/parse with a fake transport.

**Files:**
- Create: `src/rmu/onboard/axis_providers.py`
- Modify: `src/rmu/ai/doctor.py` (add a vision-model line)
- Test: `tests/unit/test_axis_providers.py`

**Interfaces:**
- Consumes: `rmu.ai.config.load_ai_config`, `store_root`, `has_consent`; `AxisInterpreter` (Task 4); `LocalLLM`-style structured output.
- Produces:
  - `resolve_axis_interpreter(mode: str, config, *, client: str | None) -> AxisInterpreter | None` — `none`/`--no-ai` → `None`; `local` → `LocalVisionInterpreter` (or `None` if unavailable); `external` → consent-gated interpreter, raising `ConsentRequired` when no consent recorded (mirrors `map start --assist external`).
  - `LocalVisionInterpreter(host, model, timeout)` with `.available() -> bool` and `.interpret(grid, page_image_png) -> dict | None` using Ollama structured output constrained to the design's JSON schema. `page_image_png=None` falls back to a text-grid prompt.
  - `AXIS_SCHEMA` — the jsonschema for the interpreter output (row_axis/col_axis/entries).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_axis_providers.py
import pytest
from rmu.onboard.axis_providers import resolve_axis_interpreter, ConsentRequired, AXIS_SCHEMA
from rmu.ai.config import AIConfig

def _cfg(consent=None):
    return AIConfig(default_mode="local", ollama_host="http://127.0.0.1:11434",
                    embedding_model="x", llm_model="qwen2.5vl:7b", timeout_seconds=60,
                    external_provider="anthropic", external_model=None,
                    consent=consent or [])

def test_none_mode_returns_no_interpreter():
    assert resolve_axis_interpreter("none", _cfg(), client=None) is None

def test_external_without_consent_refuses():
    with pytest.raises(ConsentRequired):
        resolve_axis_interpreter("external", _cfg(), client="acme")

def test_axis_schema_shape():
    assert AXIS_SCHEMA["type"] == "object"
    assert "row_axis" in AXIS_SCHEMA["properties"]
    assert "col_axis" in AXIS_SCHEMA["properties"]
```

Note: match the real `AIConfig` field names by reading `src/rmu/ai/config.py` before writing this test; adjust the constructor kwargs to the dataclass as-defined.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_axis_providers.py -v`
Expected: FAIL with `ModuleNotFoundError: rmu.onboard.axis_providers`

- [ ] **Step 3: Implement `axis_providers.py`**

```python
# src/rmu/onboard/axis_providers.py
"""Resolve the AxisInterpreter for the matrix interpret stage (feature 005).

Mirrors the 002 assist-mode precedence: none/--no-ai -> no interpreter; local ->
loopback Ollama vision model (default qwen2.5vl:7b); external -> consent-gated
(template-only). Local guarantee (FR-002) is inherited from LocalLLM's loopback
pinning. External here is a thin wrapper flagged for the consent gate; the actual
Anthropic vision call is added when external is enabled.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

from rmu.ai.config import is_loopback  # loopback predicate (config.py)

AXIS_SCHEMA = {
    "type": "object",
    "properties": {
        "row_axis": {"type": "object", "properties": {
            "number_column": {"type": ["integer", "null"]},
            "text_column": {"type": "integer"},
            "header_rows": {"type": "array", "items": {"type": "integer"}},
            "entries": {"type": "array", "items": {"type": "object", "properties": {
                "row": {"type": "integer"}, "number": {"type": ["string", "null"]},
                "label": {"type": "string"}, "confidence": {"type": "number"}},
                "required": ["row", "label"]}}}},
        "col_axis": {"type": "object", "properties": {
            "entries": {"type": "array", "items": {"type": "object", "properties": {
                "col": {"type": "integer"}, "label": {"type": "string"},
                "confidence": {"type": "number"}}, "required": ["col", "label"]}}}},
        "notes": {"type": "string"},
    },
    "required": ["row_axis", "col_axis"],
}

_PROMPT = (
    "You are given a form table extracted from a PDF as a 2-D grid of cell text "
    "(row index i, column index j). It is a criteria x asset matrix: some left "
    "columns hold a criterion number and its text; some top rows are asset/tower "
    "headers; the rest are answer cells. Identify the row axis (criteria) and "
    "column axis (towers), labelling each BY ITS INDEX. Never invent an index "
    "that is not in the grid. Grid:\n{grid}\n"
)


class ConsentRequired(RuntimeError):
    """External assist requested for a client without recorded consent."""


class LocalVisionInterpreter:
    def __init__(self, host: str, model: str, timeout_seconds: int = 120):
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout_seconds
        self.loopback = is_loopback(__import__("urllib.parse", fromlist=["urlparse"]).urlparse(self.host).hostname)

    def available(self) -> bool:
        if not self.loopback:
            return False
        try:
            with urllib.request.urlopen(f"{self.host}/api/tags", timeout=5) as resp:
                names = {m.get("name", "") for m in json.loads(resp.read()).get("models", [])}
        except (urllib.error.URLError, OSError, ValueError):
            return False
        repo = self.model.split(":")[0]
        return any(n == self.model or n.split(":")[0] == repo for n in names)

    def interpret(self, grid, page_image_png=None):
        body = {"model": self.model, "stream": False, "format": AXIS_SCHEMA,
                "options": {"temperature": 0},
                "prompt": _PROMPT.format(grid=json.dumps(grid))}
        if page_image_png is not None:
            body["images"] = [base64.b64encode(page_image_png).decode("ascii")]
        data = json.dumps(body).encode()
        try:
            req = urllib.request.Request(f"{self.host}/api/generate", data=data,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(json.loads(resp.read())["response"])
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            return None


def resolve_axis_interpreter(mode, config, *, client):
    if mode in ("none",):
        return None
    if mode == "local":
        vi = LocalVisionInterpreter(config.ollama_host, config.llm_model, config.timeout_seconds)
        return vi if vi.available() else None
    if mode == "external":
        from rmu.ai.config import has_consent
        if not client or not has_consent(config, client):
            raise ConsentRequired(
                f"external assist needs recorded consent for client {client!r} "
                "(rmu ai consent grant); templates only, never client reports")
        # External Anthropic vision interpreter is added when external is enabled.
        raise ConsentRequired("external vision interpreter not yet enabled")
    return None
```

Before implementing, read `src/rmu/ai/config.py` to confirm the exact names of `is_loopback`/`has_consent` and the `AIConfig` fields; adjust imports to match (the 002 module already exposes these — reuse, do not duplicate).

- [ ] **Step 4: Add the doctor line**

In `src/rmu/ai/doctor.py`, where the local LLM is probed, add a vision-model probe line reporting `LocalVisionInterpreter(...).available()` for the configured model, labelled "vision (matrix interpret)".

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/unit/test_axis_providers.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/rmu/onboard/axis_providers.py src/rmu/ai/doctor.py tests/unit/test_axis_providers.py
git commit -m "feat(005): local vision axis interpreter + assist-mode resolution + doctor"
```

---

### Task 6: `required_schema` matrix representation + approve/verify

Register a matrix template as data so apply/render see real field names, and confirm verify-on-approve still round-trips each cell.

**Files:**
- Modify: `src/rmu/onboard/approve.py` (`approve_template` / the `required_schema` build around lines 199-324)
- Test: `tests/integration/test_matrix_onboard_e2e.py`

**Interfaces:**
- Consumes: a reviewed matrix document (axes confirmed).
- Produces: `TargetTemplate.required_schema` gains a `matrix` block: `{"criteria": [{"id","number","label"}], "towers": [{"id","label"}], "cell_field": "{criterion}__{tower}"}` alongside the existing `required` list of cell `target_field`s (so existing apply/validate keep working unchanged).

- [ ] **Step 1: Write the failing e2e test**

```python
# tests/integration/test_matrix_onboard_e2e.py
import re
from pathlib import Path
from typer.testing import CliRunner
from rmu.cli import app
from rmu.db import make_engine, make_session_factory
from rmu.models import TargetTemplate

runner = CliRunner()
FIXTURE = "tests/fixtures/onboarding/matrix_target.pdf"

def test_matrix_template_registers_with_matrix_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    monkeypatch.setenv("RMU_PROFILES", str(tmp_path / "profiles"))
    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    drafted = runner.invoke(app, ["onboard", "draft-template", FIXTURE, "--no-ai"])
    assert drafted.exit_code == 0, drafted.output
    pid = int(re.search(r"proposal: (\d+)", drafted.output).group(1))
    # confirm every element via CLI review path, then approve
    assert runner.invoke(app, ["onboard", "review", str(pid), "--confirm-all"]).exit_code == 0
    approved = runner.invoke(app, ["onboard", "approve", str(pid),
                                   "--name", "matrix.test@1", "--by", "tester"])
    assert approved.exit_code == 0, approved.output
    with make_session_factory(make_engine())() as s:
        row = s.query(TargetTemplate).filter_by(name="matrix.test").one()
    schema = row.required_schema
    assert "matrix" in schema
    assert {c["id"] for c in schema["matrix"]["criteria"]}  # criteria present
    assert {t["id"] for t in schema["matrix"]["towers"]}    # towers present
    assert all("__" in f for f in schema["required"])       # cell fields meaningful
```

Note: if `onboard review --confirm-all` does not exist, use the existing bulk-confirm/review entry point the CLI provides (read `src/rmu/onboard/cli.py`); the point is to reach an all-confirmed proposal deterministically.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_matrix_onboard_e2e.py -v`
Expected: FAIL (no `matrix` block in `required_schema`)

- [ ] **Step 3: Emit the matrix block in `approve_template`**

In `src/rmu/onboard/approve.py`, where `required_schema={"required": required}` is built, when the document contains `row_axis`/`col_axis` elements, also assemble and attach a `matrix` block from their confirmed entries:
```python
    row_axis = next((_active_payload(e) for e in _elements(document, "row_axis")), None)
    col_axis = next((_active_payload(e) for e in _elements(document, "col_axis")), None)
    schema = {"required": required}
    if row_axis and col_axis:
        schema["matrix"] = {
            "criteria": [{"id": e["id"], "number": e.get("number"), "label": e["label"]}
                         for e in row_axis["entries"]],
            "towers": [{"id": e["id"], "label": e["label"]} for e in col_axis["entries"]],
            "cell_field": "{criterion}__{tower}",
        }
    # ... use `schema` in place of the inline required_schema=...
```
Confirm `_active_payload` returns the corrected payload when the analyst edited an axis in review (it already does for regions).

- [ ] **Step 4: Run the e2e test + the full onboarding suite**

Run: `uv run pytest tests/integration/test_matrix_onboard_e2e.py tests/ -k "onboard or template or verify" -v`
Expected: PASS; verify-on-approve still round-trips each cell region (unchanged mechanism).

- [ ] **Step 5: Commit**

```bash
git add src/rmu/onboard/approve.py tests/integration/test_matrix_onboard_e2e.py
git commit -m "feat(005): register matrix schema on approve; verify unchanged"
```

---

### Task 7: `--no-ai` floor + offline determinism sweep

Lock the invariants: `--no-ai` produces the deterministic axes with no `ai_assist`, and the interpret path never runs a socket in the suite.

**Files:**
- Test: `tests/invariants/test_matrix_noai_offline.py`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write the invariant tests**

```python
# tests/invariants/test_matrix_noai_offline.py
from pathlib import Path
from rmu.onboard.analyze_target import analyze
from rmu.onboard.interpret_matrix import apply_interpretation

FIXTURE = Path("tests/fixtures/onboarding/matrix_target.pdf")

def test_noai_reconstruction_is_deterministic_and_unassisted():
    a = analyze(FIXTURE, kind="fixed_layout")
    b = analyze(FIXTURE, kind="fixed_layout")
    assert a == b  # pure, repeatable
    for e in a["elements"]:
        assert "ai_assist" not in e.get("evidence", {})

def test_interpret_noop_without_interpreter_leaves_axes_untouched():
    doc = analyze(FIXTURE, kind="fixed_layout")
    grids = {1: [["No", "Criterion", "T1", "T2", "T3"]]}
    same, dropped = apply_interpretation(doc, grids, None)
    assert same == doc and dropped == {"unknown_index": 0}
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/invariants/test_matrix_noai_offline.py -v`
Expected: PASS

- [ ] **Step 3: Full suite + ruff**

Run: `uv run pytest -q && uv run ruff check src/ tests/`
Expected: all green, ruff clean.

- [ ] **Step 4: Commit**

```bash
git add tests/invariants/test_matrix_noai_offline.py
git commit -m "test(005): --no-ai deterministic floor + interpret no-op invariants"
```

---

### Task 8: STATUS + ASSUMPTIONS

**Files:**
- Modify: `STATUS.md`, `ASSUMPTIONS.md`

- [ ] **Step 1:** Add a STATUS.md session entry: what shipped (Phase 1 matrix onboarding), the qwen2.5vl model choice (verify tag before pinning), and that Phase 2 (studio axis review) is next.
- [ ] **Step 2:** Log the assumption that the blank Eskom target template is a form spec (not client data) and so is eligible for external template-only assist under consent (new `A#`); cite it in `axis_providers.py`.
- [ ] **Step 3: Commit**

```bash
git add STATUS.md ASSUMPTIONS.md
git commit -m "docs(005): STATUS + ASSUMPTIONS for matrix onboarding phase 1"
```

---

## Self-Review

**Spec coverage:** data model (Tasks 2,6) ✓; deterministic axis reconstruction + `--no-ai` floor (Tasks 2,3,7) ✓; interpret stage + index-gate (Task 4) ✓; tiered local/external/consent + model choice (Task 5) ✓; apply/verify unchanged + matrix schema (Task 6) ✓; data-sensitivity/offline (Tasks 5,7) ✓; synthetic fixture (Task 1) ✓. Studio matrix review is explicitly Phase 2 (separate plan). Non-goal (source→matrix mapping) not implemented, as intended.

**Placeholder scan:** two deliberate "read the real signatures before finalizing" notes (Tasks 5,6) point at exact files to confirm names against — not TODOs in shipped code. All code steps carry complete code.

**Type consistency:** `reconstruct_matrix -> list|None`, `derive_field(row_id,col_id)`, element payload keys (`row_id`/`col_id`/`target_field`), `apply_interpretation(document, grids, interpreter, images) -> (document, dropped)`, and `resolve_axis_interpreter(mode, config, *, client)` are used consistently across tasks.

## Open items to confirm during execution
- Exact `AIConfig` field names + `is_loopback`/`has_consent` exports in `src/rmu/ai/config.py` (Task 5).
- The CLI entry point for "confirm all elements" in `onboard review` (Task 6) — use whatever the existing CLI provides.
- Whether `target_grid.pdf`'s existing tests assert flat-region counts that now change to matrix output (Task 3) — update them to the matrix shape.
