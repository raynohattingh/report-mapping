# Implementation Plan: AI-Assisted Onboarding of New PDF Source Shapes and Target Formats

**Branch**: `003-pdf-format-onboarding` | **Date**: 2026-07-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/003-pdf-format-onboarding/spec.md`

## Summary

Add a draft → review → approve onboarding path for (a) unrecognised structured source PDFs and (b) PDF target formats (fillable-form and fixed-layout), so a never-seen format costs minutes of human validation instead of hand-built code. Technical approach: deterministic structural heuristics (pdfplumber word/line geometry) propose an extraction recipe or template schema as a **data artifact**; the existing 002 local-AI layer optionally enriches labels/confidence; the analyst reviews via the established D1 pattern (editable YAML + generated HTML review sheet); approval is a machine-checked gate (verify-on-approve, FR-022) that registers a new version into the existing append-only registries. A new **generic recipe-driven extractor** interprets approved source recipes (no per-profile code), and new **PDF renderers** (pypdf form-fill, reportlab overlay) render applied batches with mandatory round-trip verification. Drafts live outside the registries and can never be referenced by an ApplyRun.

## Technical Context

**Language/Version**: Python 3.12 (uv-managed) — fixed by constitution
**Primary Dependencies**: existing — pdfplumber (analysis + extraction + text read-back), SQLAlchemy/Alembic (SQLite), Typer, PyYAML + jsonschema, 002 local-AI layer (`rmu.ai`); **new** — `pypdf` (AcroForm enumerate/fill/read-back, encryption + XFA detection), `reportlab` (fixed-layout text/image overlay). New deps justified in Complexity Tracking.
**Storage**: SQLite registries (append-only ★ tables) + `profiles/*.yaml` recipe files + `store/objects` (content-addressed template PDFs, extracted images) + `store/drafts` (proposal YAML, per D1)
**Testing**: pytest — golden-file tests (render), determinism tests (apply/extract), invariant tests (draft-block, append-only), round-trip tests (form + overlay)
**Target Platform**: local single-operator machine (macOS dev), per A5
**Project Type**: CLI tool extension (existing `rmu` Typer app gains an `onboard` sub-app)
**Performance Goals**: SC-009 — draft-profile analysis of a 300-page report < 10 min locally; AI enrichment self-budgets via page sampling. SC-003 — analyst review-and-approve < 30 min.
**Constraints**: no document content to third-party services (FR-020); `--no-ai` heuristics-only path always works; apply/render stay pure-deterministic; append-only registries, additive migrations only; held-out Zeitview fixture is quarantined from all dev work (SC-001)

## Constitution Check

*GATE: evaluated against constitution v1.0.0 (nine principles). Re-checked after Phase 1 — still passing.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. TBD discipline | PASS | No Annexure H / SAP content invented. Onboarded templates are built FROM client-provided PDFs as data behind the TargetTemplate registry — this feature is exactly the "real formats slot in as data" mechanism. Interim templates untouched (FR-019). |
| II. Deterministic apply | PASS | AI (local-only) exists solely in the drafting session; proposals are persisted and human-reviewed. Approved recipes/templates are interpreted by deterministic engines; verify-on-approve re-runs pure extraction. Render round-trip failure is an error, never a guess (FR-013/FR-014). |
| III. Append-only registries | PASS | Approval appends new SourceProfile/TargetTemplate versions. Draft proposals live in a NEW non-registry table (`onboarding_proposals`, mirrors MappingSession draft pattern) + `store/drafts` YAML. Alembic migration is purely additive. |
| IV. Templates/transforms are data | PASS | Recipes = schema-validated YAML in `profiles/`; PDF templates = stored PDF + JSON schema in registry columns. One generic extractor (`rmu.extract.recipe_pdf`) and two generic renderers interpret them; onboarding a new format touches zero pipeline code (FR-018). |
| V. No false confidence | PASS | Per-element confidence from structural evidence only (FR-002); low-confidence flagged, never pre-confirmed; drift still BLOCKS (FR-021 adds a recovery pointer only); fingerprint collisions rejected at approval (FR-024). |
| VI. Decoupled stages | PASS | New `rmu/onboard/` module sits beside the pipeline, producing registry artifacts only. Detect keeps its fingerprint-dict contract (onboarded fingerprints reuse the same schema). Extract gains one generic engine; Render gains two writers. No stage reaches around another. |
| VII. Data sensitivity & `--no-ai` | PASS | FR-020: heuristics always produce the base proposal; local LLM optional; `--no-ai` yields heuristics-only. Dev/test on seed + synthetic fixtures only; Zeitview held-out fixture quarantined. |
| VIII. Test-first on invariants | PASS | Failing tests precede code for: draft-block (SC-006), verify-on-approve gate, extraction determinism of recipe engine, render round-trip, golden overlay output, scopito v2020 + interim template regression (SC-007). Cut order D3 — these are never cut. |
| IX. Assumption traceability | PASS (action required) | D5 (human approval mandatory) and D6 (new PDF libs pypdf/reportlab) MUST be logged in ASSUMPTIONS.md as the FIRST implementation task, before any code cites them. |

## Project Structure

### Documentation (this feature)

```text
specs/003-pdf-format-onboarding/
├── spec.md              # Feature specification (clarified + 3 brainstorm rounds)
├── plan.md              # This file
├── research.md          # Phase 0 — decisions on PDF libs, heuristics, XFA detection
├── data-model.md        # Phase 1 — onboarding_proposals table, registry extensions
├── quickstart.md        # Phase 1 — end-to-end onboarding walkthrough
├── contracts/
│   ├── recipe.schema.json        # Source extraction recipe (profile YAML) schema
│   ├── pdf-template.schema.json  # PDF TargetTemplate config schema (form/overlay)
│   ├── proposal.schema.json      # Draft proposal document schema (both kinds)
│   └── cli-onboard.md            # CLI contract for the onboard sub-app
└── tasks.md             # (/speckit-tasks output — not created here)
```

### Source Code (repository root)

```text
src/rmu/
├── onboard/                    # NEW module — the whole drafting lifecycle
│   ├── __init__.py
│   ├── analyze_source.py       # structural heuristics → draft extraction recipe
│   ├── analyze_target.py       # AcroForm enumeration / fixed-layout region proposal
│   ├── pdf_kind.py             # doc-kind signals, XFA/encryption/scanned diagnosis (FR-010, FR-023)
│   ├── proposal.py             # proposal load/save/validate, element review states
│   ├── review_sheet.py         # HTML review sheet w/ page snippets (mirrors mapping/review_sheet.py)
│   ├── skeleton.py             # empty-proposal skeleton + diagnosis (FR-001b)
│   ├── enrich.py               # optional 002 local-AI enrichment (naming, hints)
│   └── approve.py              # verify-on-approve gate + registration (FR-022, FR-024)
├── extract/
│   └── recipe_pdf.py           # NEW generic extractor interpreting approved recipes
├── render/
│   ├── pdf_form.py             # NEW AcroForm fill (pypdf)
│   ├── pdf_overlay.py          # NEW fixed-layout text+image overlay (reportlab + pypdf merge)
│   └── pdf_roundtrip.py        # NEW read-back verification for both kinds (FR-013)
├── detect/fingerprint.py       # UNCHANGED contract; onboarded fingerprints reuse dict schema
├── apply/engine.py             # gains draft-artifact guard error path (FR-016) — check only
└── cli.py                      # registers `rmu onboard` sub-app (draft-profile, draft-template,
                                #   review, approve) + render wiring for pdf kinds

profiles/                       # onboarded recipes land here as <key>.<version>.yaml
store/objects/                  # template PDFs + extracted record images (content-addressed)
store/drafts/                   # proposal YAML while in draft (D1 pattern)

tests/
├── unit/          (heuristics, pdf_kind diagnosis, proposal states, skeleton)
├── integration/   (draft→review→approve→extract E2E, drift→seeded re-onboarding)
├── contract/      (recipe/proposal/template schema validation)
├── golden/        (overlay text+coordinates, form fill output)
└── invariants/    (draft-block, determinism, round-trip, scopito+interim regression)
```

**Structure Decision**: one new `onboard/` module keeps the drafting lifecycle out of the pipeline stages (Constitution VI); the pipeline itself only gains data-driven engines (`extract/recipe_pdf.py`, `render/pdf_*.py`) that read registry artifacts. This mirrors how `mapping/` (session-side) already relates to `apply/` (pipeline-side).

## Execution Strategy

### TDD Requirements

- [x] `extract/recipe_pdf.py` [TDD]: determinism + correctness against analyst-confirmed elements is the product claim (SC-002); byte-identical re-extraction test first.
- [x] Draft-block guard in `apply/` [TDD]: SC-006 requires the failing test before the gate exists.
- [x] `onboard/approve.py` verify-on-approve [TDD]: gate must fail closed — tests for mismatch-returns-to-review and fingerprint collision precede implementation (FR-022/FR-024).
- [x] `render/pdf_form.py` + `pdf_overlay.py` + `pdf_roundtrip.py` [TDD]: golden-file + round-trip tests first (SC-004/SC-005).
- [x] Regression suite [TDD-first overall]: scopito v2020 + interim template byte-identical fixtures captured BEFORE any code change (SC-007 baseline).

### Parallel Execution Opportunities

- [x] Source-side (US1: analyze_source, recipe_pdf, skeleton) and target-side (US3: analyze_target, pdf_kind) share only the proposal lifecycle — parallelizable after `proposal.py` + data model land. [SUBAGENT]
- [x] `render/pdf_form.py` and `render/pdf_overlay.py` are independent of each other. [SUBAGENT]
- [x] Contract/schema tests can be written in parallel with implementation once schemas (Phase 1 contracts) are fixed.

### Human Checkpoints

1. After foundational phase — data model migration + proposal lifecycle + draft-block invariant test green; verify registry regression baseline passes.
2. After US1 — onboard a synthetic source PDF end-to-end on the dev fixtures; review the HTML sheet by eye.
3. After US3+US4 — onboard a synthetic form + fixed-layout target; inspect rendered PDFs.
4. Before merge — SC-001 acceptance on the quarantined Zeitview fixture (Rayno runs it; the fixture stays untouched by dev), full suite green.

### Review Gates

- [x] Contracts (recipe/proposal/pdf-template schemas): review before consumers are built — everything downstream interprets these. [REVIEW]
- [x] Alembic migration (additive tables/columns on ★-adjacent schema): review before applying. [REVIEW]
- [x] `apply/engine.py` guard change (touches the deterministic path): review before integration. [REVIEW]

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| New dependency `pypdf` (stack is "fixed for v1") | Enumerate/fill/read-back AcroForm fields; detect encryption and XFA. Nothing in the current stack writes PDF form fields. | pdfplumber is read-only (and reads text, not form fields); shelling out to external tools (pdftk/qpdf) adds non-Python runtime deps — worse for a single-operator local tool. To be logged as D6 in ASSUMPTIONS.md before use. |
| New dependency `reportlab` (same) | Draw text and images at absolute coordinates onto an overlay page merged with the original PDF — the fixed-layout rendering core (FR-012/FR-012a). | Building PDF content streams by hand via pypdf alone is error-prone (fonts, encodings, image placement) and would reimplement reportlab poorly; print-to-PDF via docx round-trip cannot hit registered coordinates. Same D6 entry. |

*(No other principle violations; both entries are stack extensions, not architecture deviations.)*
