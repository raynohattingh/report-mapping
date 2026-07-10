# Tasks: Report-Mapping Utility v1 — Map Once, Convert Many (Weekend Slice)

**Input**: Design documents from `specs/001-report-mapping-v1/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

## Task Format

```
[ID] [markers] [Story] Description
```

**Markers**: [P] parallelizable · [TDD] RED-GREEN-REFACTOR required · [REVIEW] human
review gate · [SUBAGENT] delegable. Story labels [US1]/[US2]/[US3] map to spec.md.

Plan phase mapping: Phase 1–2 ≙ plan P1+P2 · Phase 3 ≙ P3 · Phase 4–5 ≙ P4 ·
Phase 6 = polish (contains D3 cut #3). Invariant tests (append-only, determinism,
drift-block, exceptions report) are NEVER cut (D3).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: repo + toolchain scaffold per plan Project Structure

- [x] T001 Initialize git repo, create pyproject.toml (Python 3.12, uv; deps: typer, sqlalchemy, alembic, pdfplumber, pyyaml, jsonschema, docxtpl, openpyxl, jinja2, anthropic; dev: pytest, ruff, reportlab; `rmu` console script) and `src/rmu/` package skeleton with `detect/ extract/ mapping/ apply/ validate/ render/` subpackages + `cli.py`; `uv sync` must succeed
- [x] T002 [P] Configure ruff + pytest in pyproject.toml; create tests/ skeleton (`tests/{invariants,golden,unit,integration,fixtures}/`)
- [x] T003 [P] Create .gitignore (store/, .venv, __pycache__) and empty `store/` layout; initial commit
- [x] T004 [P] Implement src/rmu/config.py (RMU_DB_URL default `sqlite:///store/rmu.db`, store path, SQLite foreign_keys pragma) per research R9

**Checkpoint**: `uv sync && uv run pytest` runs (zero tests collected is fine).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: registries, schema, store, detection, extraction — everything every story stands on (plan P1+P2)

- [x] T005 [TDD] Write FAILING append-only invariant tests in tests/invariants/test_append_only.py: UPDATE/DELETE on SourceProfile/TargetTemplate/Transform/ValueMap AND ApplyRun raises AppendOnlyViolation (design §8 marks ApplyRun ★; analysis C2); Alembic migration walker asserts additive-only ops on ★ tables (research R2)
- [x] T006 Implement all 8 entities per data-model.md in src/rmu/models.py (fields, uniques, enums, ★ marks)
- [x] T007 [REVIEW] Implement src/rmu/db.py: engine/session factory + before_update/before_delete listeners raising AppendOnlyViolation on ★ tables — T005 tests go green; review before anything builds on the data model
- [x] T008 Create Alembic baseline migration in alembic/ (all 8 tables), additive-only
- [x] T009 [P] Implement src/rmu/store.py content-addressed blob store (`store/objects/<sha[:2]>/<sha>`, write-once) + unit tests in tests/unit/test_store.py (research R3)
- [x] T010 [P] [REVIEW] Author src/rmu/mapping/schemas/transform-v1.json + src/rmu/mapping/loader.py (validate YAML per contracts/transform-yaml.md: closed formula set, REQUIRED value-map versions, prompt decls; resolve pins against ValueMap rows) + unit tests in tests/unit/test_transform_schema.py — review before consumers exist (plan review gate 1)
- [x] T011 [P] Author profiles/scopito.pdf.powerline.v2020.yaml: detection fingerprint anchors (page-1 labels, severity overview, annotation-table header `Id, Severity, User tags, Issues, Comments, Page`), pdfplumber table settings, declared-totals fields (A1, A3; research R4)
- [x] T012 [P] Author templates/interim.defect_csv/ and templates/interim.annexc_pack/ as data: template files + required-field schemas + validation rules, both flagged INTERIM, defect vocabulary from seed/defect_codes_v1.csv (A2, Constitution I/IV)
- [x] T013 Implement seed loading + registry CLI in src/rmu/cli.py: `rmu db init`, `rmu seed load` (defect codes, both templates, scopito profile; idempotent), `rmu profile|template|valuemap list` + integration test in tests/integration/test_seed.py
- [x] T014 Implement src/rmu/detect/ fingerprint matching from profile YAML → profile-or-unknown + unit tests in tests/unit/test_detect.py (unknown → quarantine path, FR-002)
- [x] T015 [TDD] Write FAILING extraction tests in tests/unit/test_extract_scopito.py against BOTH real PDFs in seed/source_samples/: header fields present, severity vocabulary ⊆ {1..5, ?}, annotation rows parsed, `declared_counts == extracted` (A1, A3)
- [x] T016 Implement src/rmu/extract/scopito_pdf_powerline.py → NormalizedRecords JSON per contracts/normalized-records.md incl. integrity block (anchors_found/missing, declared_vs_extracted) — T015 goes green

**Checkpoint**: plan P1+P2 gates — invariant tests green, `rmu seed load` idempotent, both real PDFs extract clean. Get human approval.

---

## Phase 3: User Story 1 — One-Time Human-Approved Mapping Session (Priority: P1) 🎯 MVP

**Goal**: from ONE exemplar, a human-approved Transform v1 exists — manual `--no-ai` path FIRST, AI second, review sheet third (D3 internal cut order)
**Independent Test**: run the session on seed/source_samples/Distribution-report.pdf with `--no-ai`; an approved Transform v1 with lineage is stored (SC-001, SC-007)

- [ ] T017 [TDD] [US1] Write FAILING approval-precondition tests in tests/unit/test_approve_preconditions.py: approval refused while any required target field is unrouted OR any proposal is unreviewed OR any tier is T2/T3 (FR-007, design §7)
- [ ] T018 [P] [US1] Implement src/rmu/mapping/providers.py: ProposalProvider protocol + NullProvider (manual mode) + StubProvider (canned proposals for tests); plus invariant test tests/invariants/test_no_ai_in_apply.py asserting mechanically that no `anthropic`/network module is reachable from the import graphs of apply/, detect/, extract/, validate/, render/ (FR-020, Constitution II/VII; analysis C3; research R6)
- [ ] T019 [US1] Implement src/rmu/mapping/session.py: draft-transform builder from exemplar NormalizedRecords + template required schema (skeleton routes, constants, unmapped-required list), MappingSession persistence, every human decision recorded with timestamps (FR-004, FR-021)
- [ ] T020 [US1] Implement src/rmu/render/csv.py deterministic CSV renderer (`\n`, UTF-8, no BOM, stable column order) + unit test in tests/unit/test_render_csv.py — needed by preview and the defect-CSV target
- [ ] T021 [US1] Implement `rmu map start --profile --template --exemplar [--no-ai]` in src/rmu/cli.py: detect+extract exemplar, emit draft YAML to store, print paths (contracts/cli-commands.md)
- [ ] T022 [US1] Implement `rmu map preview --session` in src/rmu/cli.py: render exemplar through current draft to target format (FR-008)
- [ ] T023 [US1] Implement `rmu map approve --session --by` in src/rmu/cli.py: schema-validate, enforce T017 preconditions (exit 3), persist Transform vN + pinned ValueMap versions + approval metadata + session lineage (FR-009, FR-019)
- [ ] T024 [US1] Integration test tests/integration/test_manual_session.py: full manual `--no-ai` session on the Distribution exemplar → approved Transform v1, zero AI imports touched (SC-007; US1 acceptance scenarios 3/5/6)
- [ ] T025 [P] [US1] Implement AnthropicProvider in src/rmu/mapping/providers.py (anthropic SDK, model claude-fable-5, constructed only in mapping session without --no-ai; demo data only per A6) + proposal persistence with tier + one-line rationale (FR-005); tests use StubProvider only — no network
- [ ] T026 [P] [US1] Implement src/rmu/mapping/review_sheet.py Jinja2 static HTML (side-by-side exemplar values / proposal / rationale / decision state; AI-proposed visually distinct from human-confirmed) + `rmu map review` CLI (FR-006)
- [ ] T027 [US1] Integration test tests/integration/test_ai_session.py: StubProvider session → proposals require explicit decisions; resulting transform has identical form to manual one (US1 scenarios 1/2; SC-007)

**Checkpoint**: plan P3 gate — human runs the manual session end-to-end and approves Transform v1. Get human approval.

---

## Phase 4: User Story 2 — Zero-Decision Batch Conversion (Priority: P2)

**Goal**: a folder of ≥20 same-shape reports converts with zero human field decisions; exceptions reported, never guessed
**Independent Test**: `rmu apply run tests/fixtures/batch_20 …` produces per-report outputs + defect CSVs + exceptions report with no human prompt (SC-002, SC-006)

- [ ] T028 [P] [SUBAGENT] [US2] Build tests/fixtures/build_fixtures.py (reportlab, fixed random seed, dev-only) and generate+commit tests/fixtures/batch_20/ (≥18 synthetic same-structure PDFs incl. ONE zero-findings report — header + empty annotation table, declared count 0; the 2 real PDFs complete the 20) per research R7 (analysis C1)
- [ ] T029 [TDD] [US2] Write FAILING apply-invariant tests in tests/invariants/test_exceptions_report.py: OOV value → Exception with record ref/value/reason/suggestion and NO output value (FR-012); a record carrying the extractor's parse_error marker → per-record Exception while the document still converts (FR-016 record-level rule); every run emits exceptions report even when clean (FR-013)
- [ ] T030 [US2] Implement src/rmu/apply/engine.py pure function `(NormalizedRecords, Transform, prompt_answers) → TargetDraft + Exceptions`: routes, pinned value-map lookups, constants, closed-set formula evaluation (concat/substring/regex_extract/date_format/number_format/arith), OOV → Exception — no AI/network/clock imports (FR-011/FR-012; research R5)
- [ ] T031 [US2] Implement exceptions-report writer src/rmu/render/exceptions.py (per-run exceptions.csv, always written) — T029 goes green
- [ ] T032 [US2] Implement src/rmu/apply/batch.py: validate prompt answers upfront (fail fast listing missing keys), per-document detect→extract→integrity→convert-or-quarantine, duplicate fingerprints converted once + noted, empty batch reported as such (exit 1, never a success run), per-report outputs to store/runs/<id>/, ApplyRun written ONLY on completion — with a unit test in tests/unit/test_batch_atomicity.py that a simulated mid-batch failure leaves NO ApplyRun row (analysis C4) (FR-011, FR-016, FR-017; edge cases)
- [ ] T033 [US2] Implement `rmu apply run <folder> --transform [--answer k=v ...] [--label]` + `rmu runs list|show` in src/rmu/cli.py with contract exit codes (contracts/cli-commands.md)
- [ ] T034 [US2] Integration test tests/integration/test_batch.py: batch_20 through approved transform → 20 conversions, per-report defect CSVs, zero interactive prompts, exceptions.csv present; a fixture with an unmapped issue label lands in exceptions not output; the zero-findings fixture converts to a valid empty-findings output, not an error (US2 scenarios 1–4; SC-002, SC-006; spec edge case, analysis C1)

**Checkpoint**: US1+US2 work independently. Get human approval.

---

## Phase 5: User Story 3 — Trustworthy, Reproducible, Regenerable Output (Priority: P3)

**Goal**: SafeCard verdicts from value-level coverage only; drift blocked per-document; byte-identical re-runs; exact regeneration
**Independent Test**: mixed batch with drifted fixtures → drifted BLOCKED + healthy convert; double-run hashes equal; regen hash-verifies (SC-003/004/005)

- [ ] T035 [P] [US3] Generate+commit tests/fixtures/drifted/: fixture A with renamed annotation-table header (`Id`→`Ref`, anchor missing), fixture B declaring 10 annotations but containing 7 rows (count mismatch) per research R7
- [ ] T036 [TDD] [US3] Write FAILING drift-block tests in tests/invariants/test_drift_block.py: both drifted fixtures are quarantined with no output, listed in SafeCard + exceptions; healthy documents in the same batch still convert (FR-016; SC-003)
- [ ] T037 [US3] Implement src/rmu/validate/safecard.py: per-document verdict from tier coverage + value-level coverage + exception rate + integrity signals; batch summary; safecard.json writer; NO field-name-overlap input anywhere + unit tests in tests/unit/test_safecard.py (FR-015; research R10)
- [ ] T038 [TDD] [US3] Write FAILING determinism tests in tests/invariants/test_determinism.py: run batch twice → every output file sha256 identical; straight hash, no masking (FR-011; SC-004)
- [ ] T039 [US3] Implement src/rmu/render/canonicalize.py ZIP/OPC canonicalizer (sorted entries, 1980-01-01 entry dates, fixed compression, pinned docProps created/modified, stripped lastModifiedBy) wired into every renderer — T038 goes green (research R1)
- [ ] T040 [US3] Implement `rmu apply regen <run-id> [--out]` in src/rmu/cli.py: rebuild from ApplyRun (inputs by fingerprint, recorded prompt answers, pinned versions), verify each regenerated hash equals outputs_manifest, nonzero exit on mismatch, never re-asks (FR-018)
- [ ] T041 [US3] Regeneration invariant test in tests/invariants/test_regeneration.py: regen of a completed run reproduces manifest hashes exactly (SC-005)
- [ ] T042 [US3] Integration drift drill tests/integration/test_drift_drill.py: batch_20 + drifted fixtures in one run → per-document quarantine verdicts, healthy 20 convert, safecard.json batch summary + exceptions.csv each list every blocked document (US3 scenarios 1–4; SC-003)

**Checkpoint**: all three stories independently verifiable — the weekend DoD drill passes. Get human approval.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: second interim template, golden files, hygiene, hand-off state

- [ ] T043 [P] [SUBAGENT] Implement templates/interim.annexc_pack docxtpl renderer in src/rmu/render/docx.py (canonicalized) + golden-file test in tests/golden/test_annexc_pack.py — D3 cut #3: defer if Sunday slips, never at the cost of invariant tests
- [ ] T044 [P] Add golden-file tests for defect CSV + HTML review sheet in tests/golden/ (byte-exact expected outputs committed)
- [ ] T045 Execute quickstart.md end-to-end manually and fix any drift between docs and CLI behavior
- [ ] T046 [P] ruff clean, type hints complete, A#/D# assumption citations present at every reliance site (Constitution IX)
- [ ] T047 Update STATUS.md: session log (done/decisions/next/open questions) + propose the three design-refinement deltas from plan.md Deviations (CLAUDE.md rule 8)
- [ ] T048 Run full test suite; verify SC-001…SC-008 each demonstrably met; record DoD evidence in STATUS.md — record SC-001 as "session flow demonstrated; ≤2h human benchmark deferred per A7" (analysis U1)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 → Phase 2 → all stories**: foundational blocks everything.
- **US1 (Phase 3)** depends only on Phase 2. **US2 (Phase 4)** needs an approved
  transform from US1's flow (T023/T024) plus T020's CSV renderer. **US3 (Phase 5)**
  needs US2's batch runner (T032) for drill/determinism targets. **Phase 6** last
  (T043/T044 can start once render interfaces exist).

### Within-story ordering

1. [TDD] test tasks first — they must FAIL before their implementation task starts
   (T005→T006/7, T015→T016, T017→T019/23, T029→T030/31, T036→T037, T038→T039).
2. Providers/models before session/services before CLI before integration tests.
3. [REVIEW] tasks (T007, T010) pause for human review before dependents proceed.

### Parallel Opportunities

- Phase 2: T009 ∥ T010 ∥ T011 ∥ T012 after T008.
- Phase 3: T018 ∥ T020 after T017; T025 ∥ T026 after T024 (manual path is done first — D3).
- Phase 4: T028 (fixtures) ∥ T029/T030 (engine) — share only the NormalizedRecords contract.
- Phase 5: T035 ∥ T037; golden-file authoring T044 ∥ renderer work T043.

### MVP Scope

Phases 1–3 (US1): an approved, stored, human-reviewed Transform v1 from one exemplar
via the manual path — demonstrable value with zero batch machinery.

---

## Superpowers Execution

### Execution Discipline by Marker

- **[TDD]**: RED-GREEN-REFACTOR via the `test-driven-development` skill if available:
  write test → run (must FAIL) → implement → run (must PASS) → refactor. The six TDD
  pairs above are the constitution-VIII invariants; they are never cut (D3).
- **[SUBAGENT]**: T028, T043 are self-contained and delegable via
  `subagent-driven-development` if available; otherwise run sequentially.
- **[REVIEW]**: T007 (append-only data layer) and T010 (transform schema) pause for
  human review before consumers are built (plan review gates).
- **[P]**: parallel within the listed groups only.

### Checkpoint Protocol

At every phase boundary: summarize, run tests, report results, ask
"Phase [N] complete. Proceed to Phase [N+1]?" and wait for explicit approval.

---

## Notes

- Total: 48 tasks — Setup 4, Foundational 12, US1 11, US2 7, US3 8, Polish 6.
- Commit after each task or logical group; cite A#/D# in commit messages where relied on.
- Apply path (T030/T032) must never import providers, network, or clock — verified by
  T038 determinism tests and the T027/T024 integration split.
