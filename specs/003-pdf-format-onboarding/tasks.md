# Tasks: AI-Assisted Onboarding of New PDF Source Shapes and Target Formats

**Input**: Design documents from `specs/003-pdf-format-onboarding/`
**Prerequisites**: plan.md, spec.md, research.md (R1–R10), data-model.md, contracts/

## Task Format

```
[ID] [markers] [Story] Description
```

**Markers**: [P] parallelizable · [TDD] RED-GREEN-REFACTOR mandatory · [REVIEW] human review gate · [SUBAGENT] delegable
**Story labels**: [US1] source onboarding · [US2] draft safety · [US3] target onboarding · [US4] PDF rendering

## Path Conventions

Single project: `src/rmu/`, `tests/` at repository root (plan.md structure decision).

---

## Phase 1: Setup

**Purpose**: Constitutional prerequisites and dependency plumbing — nothing else may cite D5/D6 or import the new libs before these land.

- [x] T001 Log decision D5 (human approval mandatory for onboarded artifacts, by design) and D6 (add pypdf + reportlab to the fixed v1 stack, per plan.md Complexity Tracking) in ASSUMPTIONS.md (Constitution IX; FR-017)
- [x] T002 Add `pypdf` and `reportlab` to pyproject.toml via `uv add`, verify imports and versions locked in uv.lock
- [x] T003 [P] Capture SC-007 regression baseline: byte-hashes of current scopito v2020 extraction output and interim template renders on both seed fixtures into tests/invariants/baselines/, plus tests/invariants/test_regression_baseline.py asserting equality (research R10)
- [x] T004 [P] Build deterministic synthetic fixture generator in tests/fixtures/make_fixtures.py producing: two same-shape structured source PDFs + one drifted variant, one AcroForm PDF (text/checkbox/choice fields incl. required flags), one fixed-layout PDF, one encrypted PDF, one image-only PDF (reportlab/pypdf-generated, committed outputs; NEVER touches seed/source_samples/zeitview_* — quarantined for SC-001)

**Execution notes**: T003 MUST be captured before any feature code changes behaviour. T004 fixtures are the substrate for every later [TDD] task.

**Checkpoint**: baseline test green; fixtures build reproducibly.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Proposal lifecycle, schemas, diagnosis ladder, and the draft-block wall — everything every story depends on.

- [x] T005 [REVIEW] Add `OnboardingProposal` model to src/rmu/models.py (NOT in APPEND_ONLY_MODELS) + additive Alembic migration for `onboarding_proposals` per data-model.md; review migration before applying
- [x] T006 [P] Install contract schemas as package data in src/rmu/onboard/schemas/ (recipe.schema.json, proposal.schema.json, pdf-template.schema.json from specs/003-pdf-format-onboarding/contracts/) + jsonschema validation helpers in src/rmu/onboard/schemas/__init__.py, with contract tests in tests/contract/test_onboarding_schemas.py
- [x] T007 [TDD] Implement proposal lifecycle in src/rmu/onboard/proposal.py: draft YAML load/save via store/drafts (draft_ref), element review states, unresolved-elements approval blocker (FR-003/FR-005), state transitions draft→approved/abandoned only; tests in tests/unit/test_proposal.py
- [x] T008 [P] [TDD] Implement diagnosis ladder in src/rmu/onboard/pdf_kind.py per research R7 (unparseable → encrypted → XFA → form → fixed-layout → scanned) with named rejections + workarounds (FR-010) and cross-misuse signals (FR-023); tests in tests/unit/test_pdf_kind.py against T004 fixtures
- [x] T009 [TDD] Add draft-artifact pre-flight guard to src/rmu/apply/engine.py: unresolvable/unregistered artifact reference → `DraftArtifactError` naming ref + status BEFORE any record is read, exception kind `draft_artifact` (FR-016); failing test FIRST in tests/invariants/test_draft_block.py (SC-006)
- [x] T010 Scaffold `rmu onboard` Typer sub-app in src/rmu/cli.py + src/rmu/onboard/__init__.py with draft-profile / draft-template / review / approve / abandon commands wired to stubs per contracts/cli-onboard.md (exit-code contract honored)

**Execution notes**: T007/T008 parallelizable after T005–T006. T009 is the US2 invariant — its failing test is written before the guard exists.

**Checkpoint**: Foundation ready — migration applied, schemas validate, draft-block test green. Human approval before user stories.

---

## Phase 3: User Story 1 — Onboard a new source report shape (Priority: P1) MVP

**Goal**: draft-profile → review (YAML + HTML sheet) → verify-on-approve → registered SourceProfile extracting deterministically via the generic recipe engine.
**Independent Test**: onboard synthetic source fixture end-to-end; second same-shape fixture then auto-detects and extracts with zero AI; ≥80%-before-correction measured on fixtures (final SC-001 number comes from the quarantined Zeitview run at acceptance).

### Tests for User Story 1

> Write FIRST; verify they FAIL.

- [ ] T011 [P] [TDD] [US1] Heuristics unit tests in tests/unit/test_analyze_source.py: page-anatomy furniture exclusion, ruled + unruled record detection, header-field candidates, per-element structural confidence (never name-based), multi-exemplar down-scoring (FR-001/FR-002, research R3) — against T004 fixtures
- [ ] T012 [P] [TDD] [US1] Recipe engine tests in tests/unit/test_recipe_pdf.py + tests/invariants/test_recipe_determinism.py: recipe-driven extraction matches expected records, byte-identical re-runs, image-file references extracted (FR-001a, FR-004)

### Implementation for User Story 1

- [ ] T013 [US1] Implement structural analysis in src/rmu/onboard/analyze_source.py: three deterministic passes per research R3, image-region correlation with `orphan_image` flagging for unmatched images (FR-001a, edge case), fingerprint derivation as reviewable elements (FR-024), multi-exemplar cross-check with `non_generalising` flags (FR-001)
- [ ] T014 [P] [US1] Implement empty-result skeleton + diagnosis in src/rmu/onboard/skeleton.py (FR-001b); tests in tests/unit/test_skeleton.py
- [ ] T015 [P] [US1] [SUBAGENT] Implement optional 002-layer enrichment in src/rmu/onboard/enrich.py: naming/label hints only, representative-page sampling (SC-009 budget), skipped under --no-ai, provenance persisted (FR-020, research R4); tests in tests/unit/test_enrich.py with stub provider
- [ ] T016 [US1] Implement HTML review sheet for profile proposals in src/rmu/onboard/review_sheet.py (mirrors mapping/review_sheet.py; renders each element with confidence, evidence, page snippet refs)
- [ ] T017 [US1] [TDD] Implement generic recipe extractor in src/rmu/extract/recipe_pdf.py interpreting contracts/recipe.schema.json (header strategies, ruled/column-cluster records, continuation, images, furniture) — T012 tests go green; extractor_ref target for all onboarded profiles (FR-004, research R5)
- [ ] T018 [US1] [TDD] [REVIEW] Implement profile approval path in src/rmu/onboard/approve.py: unresolved-element block; deterministic re-extraction must exactly match confirmed/corrected elements; fingerprint must match all exemplars and collide with NO active profile; on success append SourceProfile row + write profiles/<key>.<version>.yaml + record approved_by/approved_at; on failure persist verify_report, stay draft (FR-017/FR-022/FR-024) — failing tests first in tests/unit/test_approve_profile.py
- [ ] T019 [US1] Complete CLI: draft-profile (multi-exemplar, --no-ai, --force, --seed-from pre-population per FR-021), review --regenerate-sheet, approve --as, abandon; SafeCard BLOCK output gains seeded re-onboarding hint in src/rmu/validate/safecard.py (FR-021)
- [ ] T020 [US1] Integration test in tests/integration/test_onboard_source_e2e.py: draft → simulated corrections → approve → registered profile auto-detects and extracts fixture #2 deterministically; drift fixture BLOCKS with hint; misuse warning on form input (FR-023); skeleton path on prose PDF

**Checkpoint**: US1 demo-able end-to-end on fixtures. Human approval (plan checkpoint 2).

---

## Phase 4: User Story 2 — Drafts can never touch real conversions (Priority: P2)

**Goal**: the draft/approved wall is proven, provenance is complete, and the audit trail shows proposal → approval → registry lineage.
**Independent Test**: ApplyRun against each draft kind fails before reading any record; after approval the identical run proceeds; every approved artifact exposes who/when/proposal-id.

### Implementation for User Story 2

- [ ] T021 [P] [TDD] [US2] Extend tests/invariants/test_draft_block.py: draft PROFILE and draft TEMPLATE references both raise DraftArtifactError with artifact name + status before any record read; same run succeeds after approval (SC-006)
- [ ] T022 [P] [US2] Provenance + audit surfacing: `rmu onboard review` prints approval lineage; approved artifacts queryable by resulting_*_id with approved_by/approved_at (SC-008); abandoned-draft-has-no-effect test in tests/unit/test_proposal.py; append-only conformance of produced registry rows in tests/invariants/test_append_only_onboarded.py

**Checkpoint**: US1+US2 invariants green — the safety story is testable independent of target-side work.

---

## Phase 5: User Story 3 — Onboard a new PDF target format (Priority: P3)

**Goal**: draft-template → review → verify-on-approve (test render + round-trip) → registered TargetTemplate (pdf_form or pdf_overlay) with schema, rules, cardinality.
**Independent Test**: form fixture yields field schema with PDF-declared hints; fixed-layout fixture yields coordinate regions; both approve into registry rows validating against contracts/pdf-template.schema.json.

### Tests for User Story 3

- [ ] T023 [P] [TDD] [US3] Target analysis tests in tests/unit/test_analyze_target.py: AcroForm enumeration incl. required/kind/options/max-len hints marked source=pdf_declared (FR-007/FR-025); fixed-layout label+region proposal with page coordinates and text/image kinds (FR-008); rejection diagnoses for encrypted/XFA/scanned (FR-010)

### Implementation for User Story 3

- [ ] T024 [US3] Implement target analysis in src/rmu/onboard/analyze_target.py (pypdf field enumeration; pdfplumber label-adjacent blank-region proposal for fixed layouts; `region_too_small` flag on image regions below legibility threshold per aspect-ratio edge case; routes through pdf_kind ladder)
- [ ] T025 [P] [US3] Extend review sheet for template proposals in src/rmu/onboard/review_sheet.py: field table for forms, page-image region overlays for fixed layouts
- [ ] T026 [US3] [TDD] [REVIEW] Template approval path in src/rmu/onboard/approve.py: unresolved block; sample-value test render + round-trip gate (depends on T028/T029 render cores); on success register TargetTemplate (template_files per contracts/pdf-template.schema.json incl. pdf_object + cardinality, required_schema, validation_rules from reviewed elements per FR-025, interim=false) — tests first in tests/unit/test_approve_template.py
- [ ] T027 [US3] Complete draft-template CLI + integration test tests/integration/test_onboard_target_e2e.py: form and fixed-layout fixtures onboarded end-to-end; misuse warning on source-like input (FR-023)

**Checkpoint**: US3 registers both PDF template kinds. (T026 gate needs US4 render cores — see Dependencies.)

---

## Phase 6: User Story 4 — Produce filled PDFs from an applied batch (Priority: P4)

**Goal**: deterministic form-fill and coordinate-overlay rendering with mandatory round-trip verification and exception surfacing.
**Independent Test**: applied fixture batch renders per-record PDFs; read-back equals records exactly; golden text+coordinate comparison passes; re-run byte-identical.

### Tests for User Story 4

- [ ] T028a [P] [TDD] [US4] Golden + round-trip tests FIRST: tests/golden/test_pdf_form_golden.py (field values read back exactly, SC-004), tests/golden/test_pdf_overlay_golden.py (frozen text+bbox tuples, image presence/content hash, SC-005), tests/invariants/test_render_determinism.py (byte-identical re-runs with pinned metadata, FR-015, research R9)

### Implementation for User Story 4

- [ ] T028 [US4] [TDD] Implement AcroForm fill in src/rmu/render/pdf_form.py (pypdf, NeedAppearances, deterministic metadata per R9)
- [ ] T029 [P] [US4] [TDD] Implement fixed-layout overlay in src/rmu/render/pdf_overlay.py (reportlab invariant mode + pypdf merge; text regions with font/align config; image regions scaled-to-fit-no-crop per FR-012a)
- [ ] T030 [US4] Implement read-back verification in src/rmu/render/pdf_roundtrip.py for both kinds (string-exact fields; region text within bbox ±2pt; image overlap + content hash) — runs on EVERY render, failure = exception kind `render_roundtrip` (FR-013, research R8)
- [ ] T031 [US4] Wire PDF template kinds into apply/render flow: cardinality per_record (one PDF per record, batch naming) / per_batch; missing-required-value, oversize-value, missing-image exceptions into the existing exceptions report (FR-014); outputs_manifest kinds pdf_form/pdf_overlay; integration test tests/integration/test_render_pdf_e2e.py

**Checkpoint**: full pipeline demo — onboard source + target, apply batch, rendered verified PDFs. Human approval (plan checkpoint 3).

---

## Phase 7: Polish & Cross-Cutting

- [ ] T032 [P] SC-009 performance check: generate a ~300-page synthetic report via make_fixtures.py, assert draft-profile analysis (heuristics + sampled enrichment stub) completes < 10 min in tests/integration/test_perf_smoke.py (marked slow)
- [ ] T033 [P] [SUBAGENT] Run quickstart.md end-to-end on fixtures verbatim; fix doc drift; ruff clean; full test suite green incl. SC-007 regression baseline unchanged
- [ ] T034 Prepare (do not run) the SC-001 acceptance protocol: scripts/acceptance_003.md checklist for the Rayno-only quarantined-Zeitview run (draft → count correct records ≥80% → validate → approve → 100% validated-subset check); verify no repo code references the quarantined file (grep test in tests/invariants/test_quarantine.py)
- [ ] T035 Update STATUS.md (done/decisions/next/open questions incl. D5/D6 landed, SC-001 pending Rayno acceptance run) per CLAUDE.md rule 8

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 → Phase 2 → stories**: T001 blocks everything (Constitution IX); T003 baseline before ANY behaviour change; Phase 2 blocks all stories.
- **US1 (Phase 3)**: independent after Phase 2 — the MVP.
- **US2 (Phase 4)**: T021 needs a draft template stub from T024 for the template half; otherwise independent (T009 delivered the core wall in Foundational).
- **US3 (Phase 5)**: T026's verify gate calls the US4 render cores — order T028a/T028/T029/T030 BEFORE T026, or land T026 with the gate stubbed-failing. Recommended global order: Phase 3 → Phase 6 (render cores) → Phase 5 (approval gate) → remaining Phase 4/7.
- **US4 (Phase 6)**: render cores depend only on Phase 2 + registered-template fixtures (can use hand-written template configs before US3 exists — they're just data).

### Within Each Story

Tests ([TDD]) fail first → models → services → CLI → integration. [REVIEW] tasks (T005 migration, T018/T026 approval gates) pause for human review.

### Parallel Opportunities

- Phase 1: T003 ∥ T004. Phase 2: T007 ∥ T008 after T005/T006.
- After Phase 2: US1 source-side and US4 render cores are disjoint file sets — two [SUBAGENT] streams.
- Within US1: T014 ∥ T015 ∥ T016 after T013. Within US4: T028 ∥ T029.

---

## Superpowers Execution

### Execution Discipline by Marker

- **[TDD]**: RED-GREEN-REFACTOR via the test-driven-development skill; the invariant tests (T009, T012, T021, T028a) are constitution-VIII items — never cut, never weakened.
- **[SUBAGENT]**: T015, T033, and the US1 ∥ US4 streams may be dispatched via subagent-driven-development.
- **[REVIEW]**: T005 (migration), T018/T026 (approval gates — the safety-critical registration paths) pause for human approval.
- **[P]**: parallel within phase only, respecting listed dependencies.

### Checkpoint Protocol

At each phase boundary: summarize, run tests, report, ask "Phase N complete. Proceed?" — explicit approval required (plan.md Human Checkpoints 1–4). Final pre-merge gate includes the Rayno-only SC-001 acceptance run.

---

## Cross-Task Interfaces

> Produces/Consumes contracts so parallel workers use identical names and types. A task implementer sees only their task — these signatures are binding.

```python
# onboard/proposal.py (T007) — produces:
class Proposal:            # wraps proposal.schema.json document
    id: int; kind: str; status: str; elements: list[Element]
    def unresolved(self) -> list[str]           # element ids still 'proposed'
    def save_draft(self) -> str                 # writes store/drafts, returns draft_ref
    @classmethod
    def load(cls, proposal_id: int) -> "Proposal"

# onboard/pdf_kind.py (T008) — produces:
def diagnose(pdf_path: Path) -> Diagnosis       # .kind: 'form'|'fixed_layout'|rejection
                                                # .rejection: str|None  .workaround: str|None
def misuse_warning(kind: str, command: str) -> str | None   # FR-023 signal

# onboard/analyze_source.py (T013) — produces:
def analyze(exemplars: list[Path], *, no_ai: bool, seed_from: SourceProfile | None) -> Proposal

# onboard/analyze_target.py (T024) — produces:
def analyze(target: Path, *, no_ai: bool) -> Proposal

# extract/recipe_pdf.py (T017) — produces (consumed by approve + apply pipeline):
def extract(pdf_path: Path, recipe: dict) -> NormalizedRecords   # recipe = validated recipe YAML dict

# onboard/approve.py (T018/T026) — produces:
def approve_profile(proposal: Proposal, key: str, version: str, operator: str) -> SourceProfile
def approve_template(proposal: Proposal, name: str, version: int, operator: str) -> TargetTemplate
# both raise VerifyFailure(report: dict) -> proposal stays draft, verify_report persisted

# render/pdf_form.py (T028) / pdf_overlay.py (T029) — produce:
def render(template: TargetTemplate, records: list[dict], out_dir: Path) -> list[Path]

# render/pdf_roundtrip.py (T030) — produces:
def verify(template: TargetTemplate, pdf_path: Path, record: dict) -> RoundTripReport  # .ok: bool, .mismatches: list

# apply/engine.py (T009) — produces:
class DraftArtifactError(Exception): ...        # message names ref + status (FR-016)
```

## Notes

- MVP scope = Phase 1 + Phase 2 + Phase 3 (US1): source onboarding alone already delivers the headline value.
- 36 tasks total: Setup 4 · Foundational 6 · US1 10 · US2 2 · US3 5 · US4 5 (incl. T028a) · Polish 4.
- Commit after each task or logical group; every commit citing an assumption references A#/D# (Constitution IX).
- The quarantined Zeitview fixture is NEVER read by any task except the human-run acceptance protocol (T034 prepares it; Rayno executes it).
