# Grid-region detection for fixed-layout target templates

**Date:** 2026-07-14 · **Status:** approved · **Feature context:** 003-pdf-format-onboarding

## Problem

`rmu onboard draft-template` on a line-drawn grid form (e.g.
`seed/holdout/Eskom-Transmission-Distribution.pdf`, a 4-page inspection
checklist) produces an empty proposal: only the default `cardinality` element.

Root cause: `analyze_target.py::_fixed_layout_elements` detects fillable areas
only as "`Label:` text + adjacent area-rectangle" pairs. The Eskom form draws
its grid as ~500 1pt filled hairline rects (lines, not boxes) per page — zero
pass the `width>20 AND height>8` box filter, and its field labels are grid
row/column headers, not `Label:` lines. Yet the structure is recoverable:
pdfplumber `find_tables(strategy="lines")` reconstructs the grid — 458 cells
across 4 pages, 373 of them blank (fillable).

## Accepted success bar (user decision)

Reviewable regions, human names them: every fillable (blank) cell becomes a
proposed `overlay_region` with bbox + page + a best-effort label guess; the
analyst confirms/renames/prunes in the existing HIL review flow. No more empty
skeleton. All blank cells are proposed, filtered only by a minimum size — no
cap, no label-based dropping.

## Design

### Trigger: fallback only

`_fixed_layout_elements` runs the existing label+box pass first. Only if it
yields **zero** regions does the new `_grid_region_elements()` pass run.
Simple label-box templates (and their fixtures/tests) are untouched.

### Grid reconstruction

Per page: `page.find_tables(table_settings={"vertical_strategy": "lines",
"horizontal_strategy": "lines"})` → cells. A cell is **blank** when its crop's
`extract_text()` is empty/whitespace. Deterministic geometry; no AI
(Constitution II is apply-time, but analysis heuristics are deterministic by
design — research R3).

### Cell selection

Every blank cell becomes an `overlay_region`, except degenerate cells below
`MIN_CELL` = width ≥ 12pt AND height ≥ 8pt (can't hold a value). No cap.

### Best-effort label association

Per blank cell, first match wins:
1. `row_label` — nearest non-empty cell to the LEFT in the same row
2. `col_header` — nearest non-empty cell ABOVE in the same column
3. `positional` — fallback name `cell_p{page}_r{row}_c{col}`

Label text is truncated (60 chars) and slugified into `target_field`.
Collisions get a numeric suffix (`_2`, `_3`, …) so every `target_field` is
unique. Nothing is dropped for lacking a label.

### Element shape

Same `overlay_region` payload the pipeline already renders:

```yaml
payload:
  label: <best-effort or positional>
  target_field: <slug>
  kind: text        # grid cells are text; image kind stays a box-pass concept
  page: <n>
  bbox: [x0, height-bottom, x1, height-top]   # existing PDF-origin convention
confidence: 0.6     # geometry-reconstructed; above the 0.5 low-confidence floor
evidence:
  pages: [n]
  source: heuristic
  association: row_label | col_header | positional
  row: <r>
  col: <c>
```

### Isolation

New logic is a self-contained `_grid_region_elements(pdf_path) -> list[dict]`
in `analyze_target.py`; `_fixed_layout_elements` calls it as the fallback.

## Testing (TDD)

- New committed fixture `target_grid.pdf` (`tests/fixtures/make_fixtures.py`):
  a small line-drawn grid — labeled rows, a header row, blank answer cells,
  one degenerate (too-small) column — drawn with LINES only (no area rects),
  reproducing the Eskom shape. Existing fixtures stay byte-identical.
- Unit (`tests/unit/test_analyze_target.py`): blank cells → regions; filled
  cells skipped; degenerate cells filtered; row-label association; col-header
  association; positional fallback; unique target_fields; existing label-box
  fixture still uses the box path (fallback not triggered).
- E2E (`tests/unit/test_approve_template.py` or integration): analyze →
  confirm all → `approve_template` registers a `pdf_overlay` template whose
  verify (sample render + roundtrip) passes.
- Read-only verification against the real Eskom PDF: proposal has hundreds of
  regions (~373 minus degenerate), each with bbox/page/label.

## Out of scope

- Auto-derived semantic field names (user chose human-names-them).
- A "table region" template concept (per-cell regions only).
- Changes to AcroForm path, renderers, template model, or review/approve flow.
- The real Annexure H pro forma remains TBD-1; this improves the generic
  fixed-layout analyzer only.
