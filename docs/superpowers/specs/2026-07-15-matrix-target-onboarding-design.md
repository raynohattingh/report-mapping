# Matrix-aware target onboarding (axis reconstruction)

**Date:** 2026-07-15
**Branch:** `005-matrix-target-onboarding`
**Status:** Design approved (brainstorm), pending implementation plan.

## Problem

The Eskom Annexure-style target is a **2-D matrix**, not a bag of fields: rows are
inspection **criteria** (each with a number, e.g. `4.2 Corrosion`), columns are
**towers** (assets), and each cell is an answer slot addressed by *both* axes.

Today's onboarding (feature 003, `analyze_target._grid_region_elements`) reconstructs
the line-grid deterministically and emits every blank cell as a flat `overlay_region`
named best-effort from a *single* nearest label — row **or** column, never both. On the
real Eskom holdout this yields **373 regions named things like `10_10`**: the geometry
is right, but the **topology and names are useless** — nothing knows which cell is
`(criterion × tower)`. Detection (finding cells) is acceptable; the gap is *structural
interpretation*.

`enrich.py` (FR-020) cannot close this gap: it only suggests **names** for elements the
heuristic already found — it never proposes or fixes **structure**, so it just puts a
nicer label on the wrong thing.

## Goals

- Reconstruct the form's two **axes** (criteria, towers) and derive every cell's identity
  `(row_id, col_id)` → meaningful field names (`corrosion__tower_100`).
- Let AI **understand the structure** of a complex form (not just label it), grounded so
  it can never hallucinate coordinates.
- Collapse review from ~373 cells to **~25 axis decisions** (SC-008: holdout review < 30
  min).
- Preserve every invariant: deterministic apply (no AI at apply, Constitution II),
  templates-as-data (IV), decoupled stages (VI), local-first + `--no-ai` floor + external
  consent-gated (rule 7 / Constitution VII), append-only versioned registries (III).

## Non-goals

- **Mapping** a source report *into* the matrix (one report per tower-column vs. filling
  the whole grid) — that is a mapping-session concern, out of scope here. This feature
  only makes the target's structure legible.
- The v2 classification engine — untouched.
- Inventing the real Annexure H pro forma (TBD-1) — we build against the onboarded Eskom
  checklist holdout + synthetic fixtures only.

## Core idea: structure is AI-interpreted, geometry is deterministic

pdfplumber's `find_tables` already returns every cell's **text + exact bbox + `(i,j)`
index**. The AI reasons over *that grid* (plus the page image) and proposes the matrix
**topology by referencing cells by index** — it understands the map; pdfplumber measures
it. The model never emits a coordinate.

## Data model (Section 1)

The proposal document and registered `TargetTemplate.required_schema` gain a matrix
representation (additive; flat templates like `interim.defect_csv` are untouched):

- **`row_axis` element (criteria)** — ordered list; per content row `{ id, number,
  label, y_band, review_state, suggested_* }`. The criterion number-column and text-column
  collapse into one entry.
- **`col_axis` element (towers)** — per content column `{ id, label, x_range,
  review_state, suggested_* }`.
- **Cell regions** — still `overlay_region` (bbox from pdfplumber, unchanged), but payload
  references `{ row_id, col_id }`; `target_field` derives as `{row_id}__{col_id}`.

Reviewable units become the two axis lists (~25), not the cells (~373). Cells inherit.

## Pipeline (Section 3) — decoupled stages

`analyze` (structure) → `interpret` (optional AI) → `review` → `approve` / verify →
`register`. Only additive changes to the 003 spine:

1. **`analyze_target` matrix path** — when the line-grid fallback fires: reconstruct the
   grid, run **deterministic axis detection** (top rows = tower header band; left columns
   = criterion number+text band), emit `row_axis` + `col_axis` + cell refs. Always-on
   floor; works under `--no-ai`.
2. **`interpret_matrix.py`** — a new optional stage, sibling to `enrich.py`, same
   contract (suggests, never overwrites, never confirms; skipped `--no-ai`; no-op when no
   model).

## The interpret stage (Section 2, detailed)

**Inputs (per page):** (a) the deterministic grid as a 2-D array of cell text with each
cell's `(i,j)` + blank/fillable flag; (b) the **page image** (vision tier); (c) the
deterministic axis draft (so the model corrects, not starts cold). Page-sampling caps
token cost on large forms (as `enrich`'s 6-page budget).

**Output (index-referenced JSON, never coordinates):**

```json
{
  "row_axis": {
    "number_column": 0, "text_column": 1, "header_rows": [0, 1],
    "entries": [ {"row": 3, "number": "4.2", "label": "Corrosion", "confidence": 0.92} ]
  },
  "col_axis": {
    "entries": [ {"col": 4, "label": "Tower 100", "confidence": 0.8} ]
  },
  "notes": "col 6 header spans cols 6-7 (merged); col 2 is a unit column, not a tower"
}
```

**Binding (deterministic):** every `row`/`col` is an index into pdfplumber's grid →
criterion y-band = row range, tower x-range = column range, answer cell `(i,j)` = exact
pdfplumber bbox. `target_field` = `{criterion_id}__{tower_id}`.

**Validation gate (from the 002 proposal gate):** JSON-schema check + **referent
resolution** — every `(row,col)` cited must exist in the extracted grid; anything else is
**dropped and counted**, never invented.

**Suggestions, not overwrites:** deterministic axes are the base; interpret output rides
alongside as `suggested_*` (provenance `ai` + confidence), pending until the human accepts.
Two flavours: per-entry **label** suggestions, and flagged **structural** suggestions
(pair number+text into one criterion; row belongs to the header band). Reject → falls back
to the deterministic structure.

**Tiers / degradation / consent:** `none|local|external` via existing resolution.
`local` default; `external` opt-in, consent-gated, **template-only** (blank form = spec,
not a client report); `--no-ai` skips → deterministic axes stand.

**Worked example (real Eskom form):** deterministic-only → bare-number criteria, garbled
tower labels (`10_10`). With interpret (vision) → `header_rows:[0,1]`, `number_column:0`,
`text_column:1`, ~20 named criteria, ~5 towers; gate confirms every `(i,j)` exists; ~373
cells derive `corrosion__tower_100`. Human confirms ~25 axis entries → approve → verify →
register `eskom.annex.c@2`.

## Model substrate (Ollama)

- **`qwen2.5vl:7b`** — new recommended local default for interpret: strongest open model
  for document/table structure, honors Ollama structured output (`format` schema), ~6 GB.
- **`qwen2.5vl:32b`** — optional upgrade for the hardest forms (needs ~24 GB+ unified mem).
- **Low-memory fallbacks:** `minicpm-v` (8B) or `granite3.2-vision:2b`.
- **`qwen3:4b`** retained for text-only tiers (value maps, grid-text interpret variant).
- **External** (Anthropic vision) stays the consent-gated escape hatch.

A 7B vision model is safe here because output is index-referenced (small, constrained),
gate-validated, and human-reviewed. **Pin the exact tag only after `ollama pull` confirms
availability/size on the target hardware.** `rmu ai doctor` reports vision-model health.

## Studio matrix review (Section 4) — Phase 2 ✅ DELIVERED 2026-07-18 (branch 006, plan docs/superpowers/plans/2026-07-18-matrix-review-phase2.md)

Axis-first, extending US4 (feature 004, now in `main`): two panels (Criteria, Towers) with
per-entry `suggested_*` shown pending + confidence; selecting a criterion highlights its
row band, a tower its column, a cell their intersection; **keyboard triage over the ~25
axis entries** (confirm/rename/reject) with structural suggestions as one-tap actions;
cells shown derived, click-to-spot-check. Delivers the SC-008 review-time win.

## Apply / verify / `--no-ai` (Section 5)

- **Apply / render unchanged** — a cell is still an overlay region (bbox + `target_field`);
  the rotation-aware `pdf_overlay` renderer already draws into regions. Determinism &
  byte-identical output preserved; **no AI at apply** (Constitution II).
- **Verify-on-approve unchanged** — per-cell test-render round-trip; the studio's per-check
  report + deep-link handles the large mismatch list (FR-035).
- **`--no-ai` floor** — deterministic axes; human renames ~25 in review; apply byte-identical.
- **Data sensitivity** — built/tested on the Eskom holdout (blank template = spec, already
  quarantined in `seed/holdout/`) + a synthetic `matrix_target.pdf` fixture. External vision
  only with consent, template-only.

## Interfaces

`AxisInterpreter` mirrors the `ProposalProvider` seam: `Local` (Ollama vision/text),
`External` (Anthropic vision, consent-gated), deterministic **`Stub`** for tests (zero
network in the suite).

## Testing

- Deterministic axis detection on the synthetic fixture (known bands → correct axes/cells).
- Interpret-gate referent-resolution drops invalid `(i,j)` and counts them (fake interpreter).
- `--no-ai` = deterministic-only, no `ai_assist` block.
- Apply determinism (golden, byte-identical).
- Verify-on-approve on a matrix template.
- Offline: interpret with non-loopback sockets blocked (local) still works/degrades.

## Phasing

- **Phase 1** — data model + `analyze` matrix path + `interpret_matrix` + `--no-ai`,
  reviewed through the *existing* generic element review (CLI/YAML). Fixes topology/names.
- **Phase 2** — the axis-first studio matrix review (SC-008 speed). ✅ Delivered 2026-07-18.

## Constraint map

| Constraint | How honored |
|---|---|
| II — deterministic apply, no AI | AI only at onboarding as reviewed proposal; apply unchanged |
| III — append-only versioned registries | new template registers as `@2`; nothing mutated |
| IV — templates are data | matrix representation is `required_schema` data, not pipeline code |
| VI — decoupled stages | `analyze → interpret → review → approve` isolated; interpret optional |
| VII / rule 7 — data sensitivity | local default, `--no-ai` floor, external consent-gated template-only |
| V — no field-name-overlap-as-confidence | AI proposes structure/labels; trust is value-level review, not name overlap |

## Open questions (for the plan)

- Exact `required_schema` matrix shape (criteria/towers lists + cell-naming rule) and its
  jsonschema.
- Whether `interpret` is one call per page or one batched call (token/latency trade-off).
- `LocalVisionLLM` shape vs. reusing `LocalLLM` with an `images=` parameter.
