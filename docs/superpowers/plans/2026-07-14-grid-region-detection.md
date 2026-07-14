# Grid-Region Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fixed-layout target templates drawn as line grids (e.g. Eskom inspection checklists) produce reviewable `overlay_region` proposals for every fillable cell instead of an empty skeleton.

**Architecture:** A new self-contained `_grid_region_elements()` pass in `src/rmu/onboard/analyze_target.py`, invoked only when the existing label+box pass finds zero regions. It reconstructs the grid with pdfplumber `find_tables(strategy="lines")`, proposes each blank size-valid cell as an `overlay_region` with a best-effort label (row-left → column-above → positional), and reuses the existing `_element`/`_slug` helpers and payload shape. Spec: `docs/superpowers/specs/2026-07-14-grid-region-detection-design.md`.

**Tech Stack:** Python 3.12, uv, pytest, pdfplumber, reportlab (fixture only).

## Global Constraints

- Analysis is deterministic heuristics; no AI proposes structure (design R3, Constitution V).
- Confidence from structural evidence only, never name similarity (Constitution V).
- Existing committed fixtures must stay byte-identical (`git status` clean for them after regeneration).
- Existing label+box behaviour and its tests must be unchanged (grid pass is a fallback only).
- Proposal documents must validate against `src/rmu/onboard/schemas/proposal.schema.json` (`validate_proposal`); if the schema rejects the new evidence keys (`association`, `row`, `col`), extend the schema — templates/schemas are data (Constitution IV).
- Run commands with `uv run …`.

---

### Task 1: Synthetic line-grid fixture

**Files:**
- Modify: `tests/fixtures/make_fixtures.py`
- Create (generated, committed): `tests/fixtures/onboarding/target_grid.pdf`

**Interfaces:**
- Produces: `tests/fixtures/onboarding/target_grid.pdf` — one A4 page, two line-drawn grids (no area rects):
  - Grid A: xs `[40, 180, 320, 460, 468]` (last column an 8pt degenerate sliver), 4 rows of 30pt starting at reportlab y=742 descending (`ys = [622, 652, 682, 712, 742]`). Row 0 header text `Item`, `Result`, `Notes` in cols 0–2; row 1 col 0 `Corrosion`; row 2 col 0 `Paint`; row 3 all blank. All other cells blank.
  - Grid B: xs `[40, 120, 200]`, ys `[340, 370, 400]` — 2×2, all cells blank (positional-fallback case).

- [ ] **Step 1: Add the builder to `make_fixtures.py`**

Add to the docstring fixture list: `- target_grid.pdf                            line-drawn grid form, no area rects`. Then add the builder (after `build_fixed`) and the call **last** in `main()` (existing shared-rng fixtures keep their draw order):

```python
def build_target_grid(path: Path) -> None:
    """Line-drawn grid form (no area rects): the Eskom-checklist shape. Grid A
    has a header row, row labels, blank answer cells and an 8pt degenerate
    sliver column; Grid B is 2x2 fully blank (positional-name fallback)."""
    c = _canvas(path)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, 800, "Inspection Grid Sheet (synthetic)")
    c.setFont("Helvetica", 9)
    xs_a = [40, 180, 320, 460, 468]
    ys_a = [622, 652, 682, 712, 742]
    c.grid(xs_a, ys_a)
    for col, text in enumerate(["Item", "Result", "Notes"]):
        c.drawString(xs_a[col] + 4, 742 - 30 + 10, text)      # header row (top)
    c.drawString(xs_a[0] + 4, 712 - 30 + 10, "Corrosion")     # row 1 label
    c.drawString(xs_a[0] + 4, 682 - 30 + 10, "Paint")         # row 2 label
    xs_b = [40, 120, 200]
    ys_b = [340, 370, 400]
    c.grid(xs_b, ys_b)                                        # 2x2, all blank
    c.showPage()
    c.save()
```

In `main()`, append after the `build_survey_indented` call:

```python
    build_target_grid(OUT / "target_grid.pdf")
```

- [ ] **Step 2: Regenerate and verify byte-identity of existing fixtures**

Run: `uv run python tests/fixtures/make_fixtures.py && git status --short tests/fixtures/onboarding/`
Expected: only `?? tests/fixtures/onboarding/target_grid.pdf` (no `M` lines).

- [ ] **Step 3: Sanity-check the fixture geometry**

Run:
```bash
uv run python -c "
import pdfplumber
pdf = pdfplumber.open('tests/fixtures/onboarding/target_grid.pdf')
pg = pdf.pages[0]
rects = [r for r in pg.rects if r['width'] > 20 and r['height'] > 8]
tables = pg.find_tables(table_settings={'vertical_strategy': 'lines', 'horizontal_strategy': 'lines'})
print('usable_rects:', len(rects), 'tables:', len(tables), 'rows:', [len(t.rows) for t in tables])
"
```
Expected: `usable_rects: 0 tables: 2 rows: [4, 2]` (order may list Grid A first). If tables merge or split differently, adjust grid coordinates until 2 tables with 4 and 2 rows are found.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/make_fixtures.py tests/fixtures/onboarding/target_grid.pdf
git commit -m "test(003): line-grid target fixture (no area rects) for grid-region detection"
```

---

### Task 2: `_grid_region_elements` (unit-tested)

**Files:**
- Modify: `src/rmu/onboard/analyze_target.py`
- Test: `tests/unit/test_analyze_target.py`

**Interfaces:**
- Consumes: `target_grid.pdf` from Task 1; existing `_element(eid, kind, confidence, evidence, payload, flags=None)` and `_slug(text)` in `analyze_target.py`; `analyze(target, *, kind)` public entry.
- Produces: `_grid_region_elements(pdf_path: Path) -> list[dict]` returning `overlay_region` elements; `_fixed_layout_elements` falls back to it when the box pass yields `[]`. Evidence gains keys `association` (`"row_label" | "col_header" | "positional"`), `row`, `col`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_analyze_target.py` (match its existing import style — it already imports `analyze`; reuse its `FIX` constant if present, else define `FIX = Path("tests/fixtures/onboarding")`):

```python
def _regions(doc):
    return [e for e in doc["elements"] if e["element_kind"] == "overlay_region"]


def test_grid_form_proposes_blank_cells_as_regions():
    """A line-drawn grid (no area rects) must yield one region per blank,
    size-valid cell — not an empty skeleton (Eskom-checklist regression)."""
    doc = analyze(FIX / "target_grid.pdf", kind="fixed_layout")
    regions = _regions(doc)
    fields = {r["payload"]["target_field"] for r in regions}
    # Grid A: rows 1-2 answer cells named by row label; row 3 by column header
    assert {"corrosion", "corrosion_2", "paint", "paint_2"} <= fields
    assert {"result", "notes"} <= fields          # row 3, cols 1-2 (col_header)
    assert "paint_3" in fields                    # row 3, col 0 (above = 'Paint')
    # Grid B: fully blank 2x2 -> positional names
    assert {"cell_p1_r0_c0", "cell_p1_r0_c1", "cell_p1_r1_c0", "cell_p1_r1_c1"} <= fields
    assert len(regions) == 11                     # sliver column filtered out
    for r in regions:
        assert r["payload"]["kind"] == "text"
        assert r["payload"]["page"] == 1
        assert len(r["payload"]["bbox"]) == 4
        assert r["evidence"]["association"] in ("row_label", "col_header", "positional")
        assert r["confidence"] == 0.6
        assert r["review_state"] == "proposed"


def test_grid_form_filled_and_degenerate_cells_skipped():
    doc = analyze(FIX / "target_grid.pdf", kind="fixed_layout")
    labels = {r["payload"]["label"] for r in _regions(doc)}
    # header/label CELLS are not regions (they contain text)...
    fields = {r["payload"]["target_field"] for r in _regions(doc)}
    assert "item" not in fields                   # header cell itself not proposed
    # ...and no region is narrower than the 12pt minimum (sliver column)
    for r in _regions(doc):
        x0, _, x1, _ = r["payload"]["bbox"]
        assert x1 - x0 >= 12


def test_grid_proposal_is_schema_valid():
    from rmu.onboard.schemas import validate_proposal

    validate_proposal(analyze(FIX / "target_grid.pdf", kind="fixed_layout"))


def test_label_box_template_does_not_trigger_grid_pass():
    """target_fixed.pdf has real label+box pairs: the box pass must keep
    handling it (no grid-evidence keys, same regions as before)."""
    doc = analyze(FIX / "target_fixed.pdf", kind="fixed_layout")
    regions = _regions(doc)
    assert regions  # box pass found regions
    assert all("association" not in r["evidence"] for r in regions)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_analyze_target.py -q`
Expected: the three new grid tests FAIL (`len(regions) == 11` → 0 regions, schema test passes or fails, box-path test PASSES); existing tests PASS.

- [ ] **Step 3: Implement `_grid_region_elements` + fallback**

In `src/rmu/onboard/analyze_target.py`, add module constants near `MIN_IMAGE_REGION`:

```python
#: a grid cell narrower/shorter than this cannot hold a value (pt)
GRID_MIN_CELL_W = 12
GRID_MIN_CELL_H = 8
#: the whole point is line-drawn grids: reconstruct cells from line strokes
_GRID_TABLE_SETTINGS = {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
```

Add the function (after `_fixed_layout_elements`):

```python
def _grid_region_elements(pdf_path: Path) -> list[dict]:
    """Fallback for line-drawn grid forms (e.g. inspection checklists): the
    label+box pass sees only 1pt hairline rects and finds nothing, yet the
    fillable areas are the grid's blank cells. Reconstruct cells from line
    strokes and propose every blank, size-valid cell as an overlay region,
    named best-effort from its row label, else column header, else position —
    the analyst renames in review (design 2026-07-14, grid-region spec)."""
    elements: list[dict] = []
    used: dict[str, int] = {}
    counter = 0
    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            height = float(page.height)
            for table in page.find_tables(table_settings=_GRID_TABLE_SETTINGS):
                text = table.extract()

                def cell_text(i: int, j: int) -> str:
                    try:
                        value = text[i][j]
                    except (IndexError, TypeError):
                        value = None
                    return " ".join((value or "").split())

                for i, row in enumerate(table.rows):
                    for j, cell in enumerate(row.cells):
                        if cell is None:  # merged/absent cell
                            continue
                        x0, top, x1, bottom = cell
                        if x1 - x0 < GRID_MIN_CELL_W or bottom - top < GRID_MIN_CELL_H:
                            continue
                        if cell_text(i, j):
                            continue  # pre-printed cell, not fillable
                        label, association = "", "positional"
                        for jj in range(j - 1, -1, -1):  # nearest left in row
                            if cell_text(i, jj):
                                label, association = cell_text(i, jj), "row_label"
                                break
                        if not label:
                            for ii in range(i - 1, -1, -1):  # nearest above in col
                                if cell_text(ii, j):
                                    label, association = cell_text(ii, j), "col_header"
                                    break
                        slug = _slug(label[:60])
                        if not slug:  # no context anywhere (or non-text glyphs)
                            slug = f"cell_p{page_no}_r{i}_c{j}"
                            label, association = slug, "positional"
                        used[slug] = used.get(slug, 0) + 1
                        if used[slug] > 1:
                            slug = f"{slug}_{used[slug]}"
                        elements.append(_element(
                            f"rgn-{counter}", "overlay_region",
                            0.6,  # geometry-reconstructed; weaker than a labeled box
                            {"pages": [page_no], "source": "heuristic",
                             "association": association, "row": i, "col": j},
                            {"label": label[:60] if label else slug,
                             "target_field": slug,
                             "kind": "text",
                             "page": page_no,
                             "bbox": [round(x0, 1), round(height - bottom, 1),
                                      round(x1, 1), round(height - top, 1)]},
                        ))
                        counter += 1
    return elements
```

Wire the fallback at the end of `_fixed_layout_elements` (replace its final `return elements`):

```python
    if not elements:
        # No label+box pairs found: try line-grid reconstruction (grid forms
        # draw their fillable cells as line strokes, not area rects).
        return _grid_region_elements(pdf_path)
    return elements
```

If `validate_proposal` rejects the extra evidence keys, extend the `evidence` object in `src/rmu/onboard/schemas/proposal.schema.json` with optional `association` (string enum `row_label|col_header|positional`), `row` (integer), `col` (integer) — additive, no existing key changes.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_analyze_target.py -q`
Expected: all PASS. If `len(regions)` differs, debug with the Step-3 sanity command from Task 1 (cell merging) before touching thresholds.

- [ ] **Step 5: Commit**

```bash
git add src/rmu/onboard/analyze_target.py tests/unit/test_analyze_target.py src/rmu/onboard/schemas/proposal.schema.json
git commit -m "feat(003): grid-region fallback - line-drawn grid cells become overlay regions"
```

---

### Task 3: End-to-end approve + full-suite regression

**Files:**
- Test: `tests/unit/test_approve_template.py`

**Interfaces:**
- Consumes: `analyze` (Task 2), existing `approve_template(session, proposal, name, version, operator)` and `Proposal.create` (see `tests/unit/test_approve_template.py` for its existing `session` fixture and helpers — reuse them).

- [ ] **Step 1: Write the failing e2e test**

Append to `tests/unit/test_approve_template.py`, reusing its existing session fixture/imports (adapt names to the file's actual helpers):

```python
def test_grid_template_onboards_end_to_end(session):
    """A line-grid target (no AcroForm, no area rects) must register as a
    pdf_overlay template whose verify render/roundtrip passes."""
    exemplar = FIX / "target_grid.pdf"
    store.put_file(exemplar)
    document = analyze(exemplar, kind="fixed_layout")
    for e in document["elements"]:
        e["review_state"] = "confirmed"
    p = Proposal.create(session, document)

    row = approve_template(session, p, "synthetic_grid", 1, "rayno")

    assert p.status == "approved" and p.row.verify_report["ok"] is True
    assert row.name == "synthetic_grid" and row.interim is False
```

- [ ] **Step 2: Run to verify current state**

Run: `uv run pytest tests/unit/test_approve_template.py -q`
Expected: new test PASSES already if Task 2 landed cleanly (it exercises no new production code — that is fine, it is the regression net for the verify gate). If it FAILS in `_verify_template` (render/roundtrip), investigate before changing anything: likely overlapping regions or font metrics; fix the FIXTURE geometry (larger cells), never the verify gate.

- [ ] **Step 3: Full suite + lint**

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: all pass, lint clean.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_approve_template.py
git commit -m "test(003): e2e - grid template registers via verify-on-approve"
```

---

### Task 4: Real-PDF verification + STATUS.md

**Files:**
- Modify: `STATUS.md`

- [ ] **Step 1: Read-only verification against the Eskom holdout**

Run:
```bash
uv run python -c "
from pathlib import Path
from collections import Counter
from rmu.onboard.analyze_target import analyze
doc = analyze(Path('seed/holdout/Eskom-Transmission-Distribution.pdf'), kind='fixed_layout')
regions = [e for e in doc['elements'] if e['element_kind'] == 'overlay_region']
assoc = Counter(r['evidence']['association'] for r in regions)
pages = Counter(r['payload']['page'] for r in regions)
print('regions:', len(regions), dict(assoc))
print('per page:', dict(sorted(pages.items())))
print('sample:', [(r['payload']['target_field'], r['payload']['page']) for r in regions[:8]])
"
```
Expected: on the order of 300+ regions spread over 4 pages (373 blank cells minus degenerate slivers), a mix of `row_label`/`col_header`/`positional`, non-garbage sample names. This is evidence for STATUS.md, not a test assertion.

- [ ] **Step 2: Update STATUS.md**

Prepend a new session section (match the existing terse style): what was broken (empty skeleton on line-grid targets), root cause (box pass sees only hairline rects), the fallback design (blank grid cells → overlay regions, row/col/positional naming, human renames in review), the Eskom verification numbers from Step 1, and pointers to the spec + plan docs.

- [ ] **Step 3: Commit**

```bash
git add STATUS.md
git commit -m "docs(003): STATUS - grid-region detection for fixed-layout targets"
```

---

## Self-Review

- Spec coverage: fallback trigger (T2 S3), grid reconstruction (T2 S3), blank+size selection (T2 S3), label ladder incl. truncation/uniqueness (T2 S3), element shape (T2 S3), fixture with degenerate column + positional grid (T1), unit tests incl. box-path non-regression + schema validation (T2 S1), e2e approve (T3), Eskom verification (T4). Covered.
- Placeholder scan: none.
- Type consistency: `_grid_region_elements(pdf_path: Path) -> list[dict]`; evidence keys `association/row/col` consistent across tasks; `analyze(target, kind=...)` signature matches existing module.
