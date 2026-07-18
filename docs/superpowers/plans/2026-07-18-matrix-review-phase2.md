# Matrix Review Phase 2 (Axis-First Studio Surface) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Review a matrix proposal as ~25 axis decisions (Criteria + Towers panels, keyboard triage, one-tap suggestion accept, row/column spatial highlight) instead of via generic element payload blobs — delivering the design's SC-008 review-speed outcome.

**Architecture:** Everything is projection + orchestration over Phase 1's data. The studio derives criterion y-bands / tower x-ranges from the cells' visual-space bboxes (nothing new stored); per-entry edits (rename, accept/reject suggestion) are composed server-side into the **existing** element `correct` action with a full `corrected_payload` — the same write path the CLI YAML hand-edit uses (D6: zero studio business logic; FR-002 interchangeability preserved). Cells stay derived and are never individually reviewed.

**Tech Stack:** FastAPI + HTMX + vendored PDF.js (feature 004 stack, D11); pytest via the `tests/studio/` fixtures.

## Global Constraints

- **D6 / FR-001..004:** the studio owns ZERO business logic; every mutation goes through the existing Proposal review methods (`confirm`/`correct`/`remove` — read `src/rmu/onboard/proposal.py` for exact names/signatures) and produces byte-identical draft YAML to a hand edit. No studio-private state.
- **FR-005/006:** draft-conflict handling and terminal-state read-only exactly as the existing proposal routes do (`routes/proposals.py` patterns).
- **Suggestions are pending until a human accepts:** accepting copies `suggested_label`/`suggested_number` into the entry's `label`/`number` inside a `corrected_payload`; rejecting strips the `suggested_*` keys; the deterministic value is never silently replaced.
- **Auth:** every new route sits behind the existing StudioAuthMiddleware (no per-route work, but the route must appear in `tests/studio/test_auth_all_routes.py`'s sweep if that test enumerates routes — read it and comply).
- **No new dependencies; no CDN assets** (D11). Type hints everywhere; files < 500 lines.
- **Tier colour language:** T0/T1 confirmed, T2 pending (AI suggestion present, undecided), T3 missing — matching FR-015/FR-017 semantics.
- **Browser-automation caveat:** PDF canvas rendering cannot be visually verified by automation (throttled IntersectionObserver — see auto-memory `studio-pdf-blank-under-automation`); verify geometry/DOM contracts via TestClient + template assertions, and add manual-checklist items for the visual layer.
- Zero network in tests; `uv run pytest tests/studio/ -q` and `uv run ruff check src/ tests/` green after every task (sole pre-existing failure: `test_seed.py::test_db_init_and_seed_load_idempotent`).

---

### Task 1: Matrix projection in studio geometry

**Files:**
- Modify: `src/rmu/studio/geometry.py` (extend `proposal_geometry`)
- Test: `tests/studio/test_matrix_geometry.py`

**Interfaces:**
- Consumes: Phase 1 elements — `row_axis` payload `{number_column, text_column, header_rows, entries:[{row,id,number,label, suggested_label?, suggested_number?, suggested_confidence?}]}`; `col_axis` payload `{entries:[{col,id,label, suggested_*?}]}`; cell `overlay_region` payloads `{row_id, col_id, target_field, label, page, bbox}`. Corrections win via the existing `_active_payload`.
- Produces: `proposal_geometry(...)` return gains a `matrix` key (or `None` when the proposal has no axis elements):

```python
"matrix": {
  "row_element_id": "rowaxis-p1-t0",
  "col_element_id": "colaxis-p1-t0",
  "row_state": "proposed" | "confirmed" | "corrected" | "removed",
  "col_state": "...",
  "criteria": [{"index": 0, "row": 2, "id": "corrosion", "number": "4.2",
                 "label": "Corrosion", "suggested_label": "…"|None,
                 "suggested_number": "…"|None, "confidence": 0.92|None,
                 "page": 1, "y_band": [y0, y1]}],
  "towers":   [{"index": 0, "col": 2, "id": "t1", "label": "T1",
                 "suggested_label": None, "confidence": None,
                 "page": 1, "x_range": [x0, x1]}],
  "cell_count": 9,
}
```

`y_band` = min/max over the y-extent of every cell bbox whose payload `row_id` matches (per page); `x_range` likewise from `col_id`. Entries with no cells (fully pre-printed row) get `y_band: None` — listed, never invented. Multiple axis-element pairs (multi-page/multi-grid): one `matrix` block per pair is out of scope — take the FIRST pair and surface `"additional_axes": <count>` so the UI can say "generic review covers the rest" honestly.

- [ ] **Step 1: Write the failing tests** — build a matrix proposal via the existing `template_proposal`-style fixture but on `tests/fixtures/onboarding/matrix_target.pdf` (add a `matrix_proposal` fixture to `tests/studio/conftest.py` mirroring `template_proposal`, CLI `onboard draft-template … --no-ai`). Assert: `geometry["matrix"]` present; 3 criteria with numbers `4.1/4.2/4.3`; 3 towers; every `y_band`/`x_range` lies inside the page dims from `geometry["exemplars"][0]["pages"]`; a flat (non-matrix) proposal (`target_grid.pdf` still qualifies — use `tests/fixtures/onboarding/survey_report_a.pdf`-style form or assert on the existing `template_proposal` fixture only if it has NO axis elements; otherwise craft a no-grid PDF) yields `matrix is None`.
- [ ] **Step 2: Run — expect KeyError/None failures.**
- [ ] **Step 3: Implement** — pure derivation inside `proposal_geometry` after the spatial/non-spatial split; helper `_matrix_projection(spatial: list[dict], non_spatial: list[dict]) -> dict | None` reading axis elements from non_spatial (they carry no bbox) and bands from the spatial cells' `row_id`/`col_id` payload keys.
- [ ] **Step 4: `uv run pytest tests/studio/test_matrix_geometry.py -v` → PASS; full studio suite green.**
- [ ] **Step 5: Commit** `feat(006): matrix projection — axis entries + derived bands in proposal geometry`.

---

### Task 2: Axis entry review routes (zero business logic)

**Files:**
- Modify: `src/rmu/studio/routes/proposals.py`
- Test: `tests/studio/test_matrix_axis_routes.py`

**Interfaces:**
- Produces: `POST /proposals/{pid}/axis/{element_id}/entries/{index}` with form `action` ∈ `rename` (+`label`, optional `number`) | `accept_suggestion` | `reject_suggestion`, and `POST /proposals/{pid}/axis/{element_id}/confirm`. Each handler: loads the proposal via the exact `_load`/lease pattern the existing element routes use; reads the element's ACTIVE payload; composes the new full entries list; calls the **existing** correct/confirm review method with that payload (never writes YAML directly); returns the same fragment/refresh shape the existing element route returns. Refusals (unknown element/index, terminal proposal) are `DomainRefusal` 422s identical in style to existing ones.

Semantics (the only logic, and it is payload composition, not domain rules):
- `rename`: entry.label = form label (entry.number = form number if provided); strip that entry's `suggested_*`.
- `accept_suggestion`: entry.label = entry.suggested_label (and number likewise if present); strip `suggested_*`; 422 if none present.
- `reject_suggestion`: strip `suggested_*` only.
- After any entry edit the element's review_state becomes `corrected` (that is what the existing correct method does); `confirm` marks the element confirmed as-is.

- [ ] **Step 1: Failing parity tests** — on the `matrix_proposal` fixture: (a) rename entry 1 via the route, then load the draft YAML and assert the axis element's `corrected_payload.entries[1].label` equals the new value and every OTHER entry is byte-identical to before; (b) accept_suggestion applies suggested→label and strips suggested_*, and the SAME result is produced by hand-writing the equivalent corrected_payload via the library call (parity, FR-001 — mirror the pattern in `tests/studio/parity.py`); (c) reject_suggestion strips only; (d) 422 on terminal proposal, unknown index, accept with no suggestion; (e) auth sweep still green.
- [ ] **Step 2: Run — 404s (routes absent).**
- [ ] **Step 3: Implement the two handlers.**
- [ ] **Step 4: Tests + full studio suite green.**
- [ ] **Step 5: Commit** `feat(006): axis-entry review routes over the existing correct/confirm path`.

---

### Task 3: Axis rail template + matrix branch of the proposal view

**Files:**
- Create: `src/rmu/studio/templates/fragments/axis_rail.html`
- Modify: `src/rmu/studio/templates/proposal.html` (render axis rail when `geo.matrix`, generic rail otherwise; both present when `additional_axes > 0`)
- Modify: `src/rmu/studio/routes/proposals.py` only if the view handler must pass extra context.
- Test: `tests/studio/test_matrix_rail_template.py`

**Interfaces:** the rail renders two panels from `geo.matrix`: Criteria (number + label, mono field id, pending chip with confidence when `suggested_label`, buttons: ✓ accept · ✕ reject · rename) and Towers (same), plus a cells summary line ("9 cells derive from these axes") and per-axis Confirm buttons posting to Task 2's routes via hx-post. Rows carry `data-axis-entry="{element_id}:{index}"`, `data-kind="criteria|towers"`, `data-state`; pending rows use tier-T2 styling, confirmed axes T0 — reusing the existing chip/stripe classes from studio.css (no new colour language).

- [ ] **Step 1: Failing template tests** — GET the proposal view for `matrix_proposal`: response contains both panel headings, all 3 criteria labels + numbers, `data-axis-entry` hooks, hx-post URLs matching Task 2's routes, and NO hx-post when the proposal is approved (read-only, FR-006). A non-matrix proposal renders the existing generic rail unchanged (regression guard: reuse an assertion from the existing onboarding-review tests).
- [ ] **Steps 2-4: red → implement → green (+ full suite).**
- [ ] **Step 5: Commit** `feat(006): axis-first review rail for matrix proposals`.

---

### Task 4: Axis triage JS — keyboard + band highlight

**Files:**
- Create: `src/rmu/studio/static/js/axistriage.js`
- Modify: `src/rmu/studio/templates/proposal.html` (load it in the matrix branch), `src/rmu/studio/static/studio.css` (band highlight styles: translucent full-row/column overlay rects, `.axis-band` / `.axis-band.col`)
- Test: `tests/studio/test_matrix_rail_template.py` (extend: script tag present only for matrix proposals)

**Interfaces:** module mirrors `triage.js`'s structure: fetch `/proposals/{pid}/geometry`; selecting an axis row (click or cursor) draws a highlight band on the rendered page — criteria: full-width rect over `y_band` on its page; towers: full-height rect over `x_range` — via the existing per-page overlay SVG layer (`window.__proposalGeo` + the `drawBoxes` layer hook pattern; scale = the mount's per-page scale, same as `overlay.js`). Keyboard over axis rows: `Y` confirm-axis (when on last pending entry) / `A` accept suggestion / `R` reject / `E` rename (prompt → Task 2 rename route) / arrows move cursor; auto-advance to next entry with a pending suggestion. Cells stay display-only; clicking a cell overlay focuses BOTH its criterion and tower rows (derive from the cell's `row_id`/`col_id` in `__proposalGeo`).

- [ ] **Step 1:** Extend the template test: matrix proposals load `axistriage.js` and not the generic `triage.js`; generic proposals unchanged.
- [ ] **Step 2:** Implement JS + CSS. JS has no automated harness (see Global Constraints) — keep every DOM contract it relies on pinned by the Task 3 template tests (`data-axis-entry`, `data-kind`, band container ids).
- [ ] **Step 3:** Full studio suite + ruff green (JS untested by pytest; template hooks are).
- [ ] **Step 4: Commit** `feat(006): axis keyboard triage + row/column band highlights`.
- [ ] **Step 5:** Append to `docs/superpowers/plans/…phase2.md` manual checklist (bottom of this file) any hook you changed.

---

### Task 5: Studio matrix journey e2e + approve polish

**Files:**
- Test: `tests/studio/test_matrix_journey.py`
- Modify (only if the e2e exposes gaps): `src/rmu/studio/routes/proposals.py`

**Interfaces:** none new — this task PROVES the surface.

- [ ] **Step 1: Write the journey test** (TestClient, no browser): create matrix draft via the initiation route (upload `matrix_target.pdf` exactly as `tests/studio/test_initiation.py` uploads), then entirely over HTTP: rename one criterion, accept one suggestion (seed suggestions by running `apply_interpretation` with `StubAxisInterpreter` against the draft through the library — the draft file is shared state, FR-002), reject one, confirm both axes, bulk-confirm/confirm remaining cell + cardinality elements, approve with `matrix.e2e@1` — assert the registered `TargetTemplate.required_schema["matrix"]` carries the RENAMED label and the ACCEPTED suggestion's label, proving review decisions flow into the registered artifact; then assert the draft YAML is loadable by `rmu onboard review` CLI (interchangeability smoke).
- [ ] **Step 2: red → fix anything it exposes → green; full suite + ruff.**
- [ ] **Step 3: Commit** `test(006): studio matrix review journey e2e`.

---

### Task 6: Docs

**Files:** `STATUS.md`, `README.md` (Mapping Studio + Matrix targets sections: one paragraph each on axis-first review), `docs/superpowers/specs/2026-07-15-matrix-target-onboarding-design.md` (mark Phase 2 delivered).

- [ ] **Step 1:** Update all three; keep STATUS terse (what shipped, the manual checklist below still open).
- [ ] **Step 2: Commit** `docs(006): phase 2 axis review shipped`.

---

## Manual verification checklist (browser; automation cannot see canvas paint)

- [ ] Selecting a criterion highlights its full row band on the rendered page; a tower its column; a cell click focuses both rows (SC-007 by eye).
- [ ] Keyboard triage (arrows / A / R / E / Y) over the axis panels, auto-advance on pending suggestions.
- [ ] Pending chips show confidence; accepting updates the label in place without a full page reload.
- [ ] Read-only (approved) matrix proposal shows panels with zero action affordances.

## Self-Review

**Spec coverage:** design §"Studio matrix review (Section 4) — Phase 2": two panels ✓ (T3), spatial cross-highlight ✓ (T4), keyboard triage over entries ✓ (T4), one-tap structural/label suggestion accept ✓ (T2/T3; structural regroup suggestions beyond label/number are NOT produced by Phase 1's interpreter, so nothing to render — noted, not built, YAGNI), cells derived + spot-check ✓ (T4), SC-008 outcome exercised by the journey ✓ (T5).
**Placeholders:** none; steps carry code/shape or point at the exact existing pattern file to mirror (conftest/parity/initiation patterns are requirements, not vagueness — the implementer must read those files regardless).
**Type consistency:** `matrix` projection shape (T1) is the single contract consumed by T2's payload composition, T3's template, T4's JS; route paths defined once in T2 and referenced verbatim in T3/T5.
