# Tasks: Mapping Studio

**Input**: Design documents from `specs/004-mapping-studio/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/http-routes.md, contracts/cli-studio.md, quickstart.md

## Task Format

```
[ID] [markers] [Story] Description
```

**Markers**: **[P]** parallelizable · **[TDD]** RED-GREEN-REFACTOR required · **[REVIEW]** human review gate · **[SUBAGENT]** delegable to a subagent.
**Story labels**: `[US1]`…`[US7]` map to spec.md user stories (US1 canvas P1, US2 preview/approve P2, US3 link detail P3, US4 onboarding review P4, US5 initiation P5, US6 dashboard P6, US7 locality/deletability P7).

## Path Conventions

Single project: `src/rmu/`, `tests/` at repository root (plan.md Project Structure). The studio is the deletable subpackage `src/rmu/studio/`; studio tests live in `tests/studio/` and skip module-wide when the `studio` dependency group is absent.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: dependency group, package skeleton, vendored assets — nothing behavioral.

- [x] T001 Log decision **D11** (FastAPI+uvicorn+python-multipart as optional `studio` dependency group; HTMX+PDF.js vendored inside `rmu.studio`) in ASSUMPTIONS.md — BEFORE any code cites it (Constitution IX; plan Constitution Check action)
- [x] T002 Add `studio` optional dependency group (fastapi, uvicorn, python-multipart) to pyproject.toml and `uv sync --group studio`; verify `uv run rmu --help` still works WITHOUT the group in a clean sync
- [x] T003 [P] Create `src/rmu/studio/` package skeleton per plan.md structure: `__init__.py`, `app.py`, `auth.py`, `launch.py`, `concurrency.py`, `geometry.py`, `routes/__init__.py`, `templates/`, `static/js/`, `static/vendor/` (empty stubs, type-hinted signatures only)
- [x] T004 [P] Vendor pinned `htmx.min.js`, `pdf.mjs`, `pdf.worker.mjs` + license files into `src/rmu/studio/static/vendor/` (research.md R2 vendoring note; record pinned versions in a VENDOR.md alongside)
- [x] T005 [P] Create `tests/studio/conftest.py` with module-wide `pytest.importorskip("fastapi")` skip + shared fixtures (seeded tmp DB, seed exemplar session factory, TestClient builder with auth cookie helper)

**Execution notes**: T003–T005 are parallel after T001–T002. Verify: suite green with and without the group before proceeding.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the invariants, security shell, concurrency primitive, parity harness, and shared-function refactors every story depends on.

**CRITICAL**: No user story work can begin until this phase is complete.

- [x] T006 [TDD] Write `tests/invariants/test_no_studio_in_core.py` — AST/import scan asserting no module under `rmu/{detect,extract,mapping,apply,validate,render,onboard,ai}` imports `rmu.studio` (pattern: existing `test_no_ai_in_apply.py`); must pass with skeleton and forever after (FR-042)
- [x] T007 [TDD] Write `tests/studio/test_deletability.py` — with `rmu.studio` importable, `rmu studio --help` works; simulate absence (monkeypatch import failure) and assert `rmu studio` exits non-zero with the `uv sync --group studio` hint while every other CLI command is unaffected (FR-042, SC-004, contracts/cli-studio.md)
- [x] T008 [TDD] [REVIEW] Implement auth middleware in `src/rmu/studio/auth.py` — tests FIRST in `tests/studio/test_auth.py`: non-loopback ASGI peer refused; forged/missing Host refused; cross-origin mutation refused (Origin/Sec-Fetch-Site); missing/stale/foreign token refused; token never written to disk; key-for-cookie exchange on `/?key=`; mutations additionally require `X-Studio-Token` header; all failures 403 with restart hint (FR-040/FR-040a, SC-003, SC-011; research.md R6)
- [x] T009 Implement `src/rmu/studio/launch.py` + register `rmu studio` in `src/rmu/cli.py` via lazy import — `secrets.token_urlsafe(32)`, hardcoded `127.0.0.1` bind (non-configurable), port pick, `--no-browser`, prints URL with `?key=` (contracts/cli-studio.md; makes T007 green)
- [x] T010 Implement FastAPI app factory in `src/rmu/studio/app.py` — Jinja2 env over `studio/templates/`, static mount, auth middleware wiring, error contract handlers (403/409/422 verbatim-domain-message/busy fragment per contracts/http-routes.md), dark-graphite base layout + nav rail template in `src/rmu/studio/templates/base.html` + `src/rmu/studio/static/studio.css` (FR-017, FR-041)
- [x] T011 [TDD] Implement DraftLease optimistic concurrency in `src/rmu/studio/concurrency.py` — tests FIRST in `tests/studio/test_concurrency.py`: SHA-256 base_hash on load; mutating request with stale hash → 409 + unified diff + reload/overwrite choices; overwrite proceeds; never silent merge/loss (FR-005; research.md R5)
- [x] T012 [TDD] Build the parity harness in `tests/studio/parity.py` — helper that runs a studio HTTP action and the equivalent CLI/library action on copies of the same draft and asserts byte-equal draft files / row-equal DB writes; first parity test (no-op draft load leaves file byte-identical); plus the bidirectional cross-surface test: session started via CLI → edited via studio → finished via CLI, and the reverse, with no reconciliation and no lost edits (FR-001/FR-002/FR-003, SC-002/**SC-005 both directions**/SC-006 foundation)
- [x] T013 [REVIEW] Extract inlined CLI orchestration into plain shared functions where the studio needs the same action (`map start` body, approve/store-Transform body, abandon transitions, valuemap create+pin, onboard draft/approve entry points) — refactor-in-place in `src/rmu/mapping/`, `src/rmu/onboard/`, `src/rmu/cli.py`; NO behavior change; existing CLI tests stay green (research.md R4)

**Execution notes**: T006–T008 and T011 are [TDD] — failing tests before implementation. T008 and T013 pause for review (security surface; touches tested CLI behavior). T012 depends on T010; T013 can run parallel to T008–T011.

**Checkpoint**: `rmu studio` launches and serves an authenticated empty shell; all invariant/auth/concurrency tests green; suite green without the group. Get human approval (plan Human Checkpoint 1).

---

## Phase 3: User Story 1 — Visual mapping canvas (Priority: P1) 🎯 MVP

**Goal**: source exemplar and target rendered side by side with element highlights; draw/accept/reject/re-route links writing the same draft the CLI edits; readiness bar from the real gate.

**Independent Test**: `rmu map start` on a seed exemplar → open studio session view → all extraction-inventory elements highlighted on rendered pages → draw one manual link, accept one AI proposal, reject another → re-read draft YAML via CLI and confirm routes/tiers/decisions changed exactly as if edited by hand (spec US1).

### Tests for User Story 1

- [x] T014 [P] [TDD] [US1] Geometry projection tests in `tests/studio/test_geometry.py` — registered visual-space bboxes (seed + rotated holdout pages) project unchanged into geometry JSON with page dims; elements without coordinates fall to the panel list; SC-007's testable half — write FIRST
- [x] T015 [P] [TDD] [US1] Route-mutation parity tests in `tests/studio/test_canvas_parity.py` (uses T012 harness) — create manual route (derived tier per FR-013a, decision `manual`), accept T2 (promote + `accepted`), reject T2 (removed + `rejected`), re-route (`edited`), delete; each byte-equal to the library-path edit; draft re-validated by `mapping.loader.parse_transform` before write
- [x] T016 [P] [TDD] [US1] Readiness/fragment tests in `tests/studio/test_fragments.py` — readiness bar numbers equal a `check_approval` dry-run on the same draft (never a parallel calculation, FR-019); link list filterable by tier/state with unmapped required fields as red entries (FR-018); golden HTML fragments for a seed fixture

### Implementation for User Story 1

- [x] T017 [US1] Implement `src/rmu/studio/geometry.py` — session geometry projection: per-page element bboxes, target field/region coords, route projections (derived tier FR-013a, stable tag numbers, state), no-coordinate fallback list (makes T014 green)
- [x] T018 [P] [US1] Implement `/documents/{sha}/pdf` in `src/rmu/studio/routes/documents.py` — stream content-addressed PDF bytes with `Cache-Control: no-store` (FR-043); 404 on unknown sha
- [x] T019 [US1] Implement session canvas routes in `src/rmu/studio/routes/sessions.py` — `GET /sessions/{id}` shell, `GET /sessions/{id}/geometry`, route-mutation POSTs (create/accept/reject/re-route/delete) delegating to draft-edit + `compute_decisions` paths with DraftLease hashes (makes T015 green; contracts/http-routes.md)
- [x] T020 [US1] Canvas templates + fragments in `src/rmu/studio/templates/session.html`, `fragments/links.html`, `fragments/readiness.html` — two PDF.js panes with independent page nav, link list between panes, readiness bar wired to `check_approval` dry-run, read-only view for approved/abandoned sessions (FR-006; makes T016 green)
- [x] T021 [US1] Client modules in `src/rmu/studio/static/js/` — `viewer.js` (lazy PDF.js page render, jump-to-element, page indicators — FR-010/SC-010), `overlay.js` (bbox × scale highlight layer, tier tags), `wires.js` (focus wire on hover/select, tri-directional selection — FR-018); no framework, no business logic
- [x] T022 [US1] Structured panels in `templates/fragments/target_panel.html` + `fragments/source_panel.html` — target-field panel for CSV/docx targets with no page representation (FR-012); source panel for no-coordinate elements including a sample of observed values per record-table column (FR-011); value-level-only fit indicators — audit canvas surfaces so no field-name-overlap signal renders (FR-016)

**Checkpoint**: US1 independent test passes end-to-end on seed data; human eyeballs overlays on the rotated holdout (plan Human Checkpoint 2). MVP delivered.

---

## Phase 4: User Story 2 — Preview and approve in the studio (Priority: P2)

**Goal**: honest native preview via the real render path; approval through the same gate storing the same Transform row.

**Independent Test**: on a studio-edited session, preview output is byte-identical to `rmu map preview` on the same draft; studio approve stores a Transform row equal to the CLI's for the same draft (spec US2).

### Tests for User Story 2

- [x] T023 [P] [TDD] [US2] Preview parity tests in `tests/studio/test_preview.py` — studio preview bytes ≡ CLI preview bytes (non-strict resolve, `<<unresolved>>` markers, count shown, render problems verbatim) for all three target kinds (FR-030)
- [x] T024 [P] [TDD] [US2] Approval parity tests in `tests/studio/test_approve.py` — gate refusals verbatim (T2/T3 remaining, unrouted required, unresolved pins); success stores row-equal Transform with approver identity; racing approval (CLI approves first) → second attempt refused by the same gate, never double-registered

### Implementation for User Story 2

- [x] T025 [US2] Implement `POST /sessions/{id}/preview` in `src/rmu/studio/routes/preview.py` + `templates/fragments/preview.html` — run non-strict resolve + real renderers into a preview area; display per kind: PDF → PDF.js pane, CSV → HTML table with flagged unresolved cells, docx → download link + unresolved count + per-field resolved values, never an HTML approximation (FR-030a; research.md R7)
- [x] T026 [US2] Implement `POST /sessions/{id}/approve` in `src/rmu/studio/routes/sessions.py` — `check_approval` + shared store-Transform function (T013), refusal reasons verbatim in the readiness-bar idiom, session status/decision updates identical to CLI (FR-031)

**Checkpoint**: full no-YAML mapping loop (US1+US2) works on seed data; CLI batch runs with the studio-approved transform (plan Human Checkpoint 3 first half).

---

## Phase 5: User Story 3 — Link detail and value mapping (Priority: P3)

**Goal**: link-level detail with observed values; staged value-map editing with explicit Register & pin; constants/formulas/per-batch prompts.

**Independent Test**: open a link with a small observed vocabulary, add one human entry, accept one AI-suggested entry, Register & pin — CLI shows a new append-only ValueMap version with correct per-entry provenance and the route pinning exactly that name@version (spec US3).

### Tests for User Story 3

- [x] T027 [P] [TDD] [US3] Value-map staging/registration parity tests in `tests/studio/test_valuemap.py` — saves stage in the session draft value-map file only (no registry write); Register & pin appends a new ValueMap version (prior versions untouched — append-only assert), entries carry `human`/`ai-accepted` provenance, route pin updated to name@version; suggested name derived from link and editable (FR-021)
- [x] T028 [P] [TDD] [US3] Mechanism parity tests in `tests/studio/test_mechanisms.py` — constant, closed-grammar formula (invalid formula rejected by the existing schema validation, verbatim error), per-batch prompt (key/label/required) land in the draft exactly as the transform schema defines; tier re-derives when mechanism changes (FR-013a recompute, FR-022)

### Implementation for User Story 3

- [x] T029 [US3] Implement link detail routes in `src/rmu/studio/routes/links.py` — `GET /sessions/{id}/links/{field}` (observed exemplar values, unmapped values conspicuous — FR-020), `POST .../valuemap` (stage), `POST .../valuemap/register` (Register & pin via shared valuemap function), `POST .../mechanism` (constant/formula/prompt)
- [x] T030 [US3] Link detail template `src/rmu/studio/templates/fragments/link_detail.html` — value-map entry table with provenance badges, AI-suggested-until-accepted marking, unmapped-observed-value warnings, mechanism editor, derived-tier display that updates on change

**Checkpoint**: US1+US2+US3 = the complete SC-001 mapping half; run plan Human Checkpoint 3 in full (value-map register & pin, preview all three kinds, approve, CLI batch).

---

## Phase 6: User Story 4 — Visual onboarding review (Priority: P4)

**Goal**: proposals reviewed on the rendered PDF — spatial overlays, keyboard triage at scale, region editing/drawing, verify-on-approve with per-check deep links.

**Independent Test**: `rmu onboard draft-template` on a seed target → review entirely in the studio (confirm/correct/remove, rename an overlay region) → approve → registered TargetTemplate matches what the YAML+CLI flow registers from the same decisions (spec US4).

### Tests for User Story 4

- [x] T031 [P] [TDD] [US4] Review-state parity tests in `tests/studio/test_onboard_review.py` — confirm/correct(payload)/remove write exactly the `review_state`/`corrected_payload` the YAML workflow writes (`Proposal.load(sync=True)` round-trip); approval blocked naming pending elements; bulk-confirm records per element indistinguishably from individual confirmation (FR-033/FR-034)
- [x] T032 [P] [TDD] [US4] Spatial-edit + verify tests in `tests/studio/test_onboard_spatial.py` — dragged/resized bbox lands as corrected_payload in registered visual space (rotated pages included); analyst-drawn element carries evidence source `analyst` and passes the same review lifecycle; failed verify-on-approve returns per-check report grouped with element deep-link ids, proposal stays draft (FR-033a/FR-035)

### Implementation for User Story 4

- [x] T033 [US4] Extend `src/rmu/studio/geometry.py` for proposals — element bboxes per page and per exemplar, cross-exemplar agreement figures, non-spatial element list with evidence/confidence/flags (FR-032/FR-032a)
- [x] T034 [US4] Implement proposal routes in `src/rmu/studio/routes/proposals.py` — `GET /proposals/{id}` (+ structureless-diagnosis view with abandon primary), `GET .../geometry`, `POST .../elements/{eid}` (confirm/correct/remove), `POST .../elements` (analyst-drawn), `POST .../bulk-confirm`, `POST .../approve` (verify-on-approve via existing gate; identity prefill from proposal context, seeded re-onboarding suggests bumped structural version — FR-035a)
- [x] T035 [US4] Triage workspace template `src/rmu/studio/templates/proposal.html` + `fragments/triage_rail.html` — PDF-first spotlight of current element, side-rail detail, state/kind/flag filters, primary-exemplar switcher with current element overlaid (FR-032a), verify-failure report grouped by page/pattern with expandable full list and deep links (FR-035)
- [x] T036 [US4] Client modules `src/rmu/studio/static/js/triage.js` (Y/E/X keyboard actions with auto-advance — FR-034) and `regions.js` (drag/resize handles + draw-new-region, pixel→registered-space conversion by zoom scale — FR-033a)
- [x] T037 [US4] Post-approval next-step offer (start a mapping session with the newly registered artifact — offered, never auto-started) in the approve response fragment (FR-035a)

**Checkpoint**: review the real Eskom holdout proposal via keyboard triage and time it — target < 30 min (SC-008; plan Human Checkpoint 4).

---

## Phase 7: User Story 5 — Start new work from the studio (Priority: P5)

**Goal**: initiate sessions and onboarding drafts (incl. seeded re-onboarding) from the studio with identical artifacts and verbatim CLI refusals.

**Independent Test**: start a session on a seed exemplar and create a draft-profile from seed exemplars in the studio; resulting rows/draft files indistinguishable from CLI-created ones (spec US5).

### Tests for User Story 5

- [x] T038 [P] [TDD] [US5] Initiation parity tests in `tests/studio/test_initiation.py` — uploaded exemplar is content-addressed identically to a CLI path-based start; session/draft/starter-value-map files byte-equal to `rmu map start`; assist mode resolved by existing precedence; drift-mismatch → same block message, no session created; unsupported PDF → same named rejection + workaround; kind-misuse warning offers explicit proceed-anyway ≡ force flag; consentless external assist → explained, not bypassed (FR-036/FR-037)

### Implementation for User Story 5

- [x] T039 [US5] Implement initiation routes in `src/rmu/studio/routes/start.py` — `POST /start/session` (multipart upload → content-addressed store → shared map-start function), `POST /start/onboarding` (draft-profile/draft-template incl. `--seed-from` path), `POST /sessions/{id}/regenerate` (same semantics/refusals as CLI, prior generation retained in assist history)
- [x] T040 [US5] Initiation templates `src/rmu/studio/templates/start.html` — profile@version/template@version pickers from registries, exemplar upload, assist-mode display with consent explanation for external (FR-036), rejection/warning surfaces reusing verbatim CLI messages

**Checkpoint**: full SC-001 journey now possible without any CLI trip except the batch itself.

---

## Phase 8: User Story 6 — Dashboard and registries (Priority: P6)

**Goal**: whole-utility situational awareness: registries, sessions/proposals by status, runs with SafeCard + exceptions, abandon, AI health + consent.

**Independent Test**: seed registries, run one CLI batch, open dashboard — every registry row, session, proposal, run verdict and exceptions content matches CLI listings; abandoning a draft shows the same terminal state to the CLI (spec US6).

### Tests for User Story 6

- [x] T041 [P] [TDD] [US6] Dashboard parity tests in `tests/studio/test_dashboard.py` — listings equal CLI/`registry` query output (versions, status, effective dates); run detail shows SafeCard batch + per-document verdicts, coverage, exceptions content; abandon ≡ CLI terminal transition; approved/registered artifacts expose zero mutating actions (FR-038/FR-039, FR-006); consent grant/revoke records same fields as CLI

### Implementation for User Story 6

- [x] T042 [US6] Implement dashboard + runs routes in `src/rmu/studio/routes/dashboard.py` — `GET /dashboard`, `GET /runs/{id}`, `POST /sessions/{id}/abandon`, `POST /proposals/{id}/abandon`; templates `dashboard.html`, `run.html` with verdict/coverage/exceptions rendering (FR-038/FR-039)
- [x] T043 [P] [US6] Implement AI health + consent routes in `src/rmu/studio/routes/ai.py` + `templates/ai.html` — `ai.doctor.health` report (embeddings, local LLM, degraded state), per-client consent status, grant/revoke via existing consent path (FR-039, FR-044)
- [x] T044 [US6] Drift-to-reonboard shortcut in run view (FR-037a) — a drift-blocked document row offers one action that opens `/start/onboarding` prefilled with the blocked document as exemplar and seed-from its drifted profile (delegates to T039; no new business logic)

**Checkpoint**: dashboard is the studio's landing page; every fact cross-checks against CLI output.

---

## Phase 9: User Story 7 — Locality and deletability (Priority: P7)

**Goal**: prove the constraints enforced since Phase 2 hold for the finished product.

**Independent Test**: non-loopback connection refused; studio package removed → full existing suite green, every CLI capability intact (spec US7).

- [x] T045 [P] [US7] Deletion drill script/CI step in `tests/studio/test_deletability.py` (extend T007) + a documented manual drill in quickstart.md — run full suite with the `studio` group not installed AND with `src/rmu/studio/` moved aside; both green (SC-004)
- [x] T046 [P] [US7] Lifecycle audit test in `tests/studio/test_lifecycle_audit.py` — walk a full studio session (initiate→map→valuemap→preview→approve) recording every filesystem/DB write; assert zero writes outside existing draft files, session/proposal rows, content-addressed objects and append-only registries (SC-006, FR-004); assert no AI provider is invoked during preview or approve actions (FR-044, extends the no-AI-in-apply invariant to the studio's request paths)
- [x] T047 [P] [US7] Browser-persistence sweep — assert `Cache-Control: no-store` on document/preview responses, no localStorage/sessionStorage use in `static/js/*` (grep-test), token absent from any persisted response body (FR-043, FR-040a)
- [x] T048 [US7] Re-verify SC-003/SC-011 against the finished route table — parametrize T008's refusal tests over every registered route (loopback, Host, Origin, token, stale URL); confirm no flag can rebind non-loopback (contracts/cli-studio.md guarantee)

**Checkpoint**: all seven stories complete; constraints proven on the finished surface.

---

## Phase 10: Polish & Cross-Cutting Concerns

- [x] T049 [P] Run the manual demo checklist in quickstart.md (rotated-overlay eyeball, SC-010 5-second open on 100+-page exemplar, SC-008 30-min triage timing, SC-009 unaided first-attempt journey) and record results in STATUS.md
- [x] T050 [P] Full SC-001 acceptance journey end-to-end on seed/synthetic data: review+approve draft profile → start session → accept ≥1 AI link → draw ≥1 manual link → value map with ≥1 human + ≥1 ai-accepted entry → one per-batch prompt field → preview → approve → CLI batch with the resulting transform; assert stored transform text identical to a CLI-built equivalent (SC-001/SC-002)
- [x] T051 [P] [SUBAGENT] Docs: update README/docs with `rmu studio` usage; ensure ASSUMPTIONS.md D11 wording matches what shipped; STATUS.md session entry (CLAUDE.md rule 8)
- [x] T052 Code cleanup — ruff clean, dead template/JS pruning, handler-thinness audit (any handler grown beyond call-existing-function-and-render is refactored per FR-001)
- [x] T053 Run the complete test suite (with and without studio group) — all green, existing determinism/append-only/drift invariants untouched

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)** → nothing; T001 first (Constitution IX), T002 second, then T003–T005 in parallel
- **Foundational (Phase 2)** → depends on Setup; **BLOCKS all stories**. Order: T006→T007 (invariants first), T008→T009→T010 (security shell), T011, T012 (needs T010), T013 (parallel track)
- **US1 (Phase 3)** → foundational only. **US2 (4)** and **US3 (5)** → depend on US1's session view. **US4 (6)** → foundational only (independent of canvas). **US5 (7)** → foundational + T013 shared functions; T044's shortcut needs T039+T042. **US6 (8)** → foundational only. **US7 (9)** → all stories (proof phase). **Polish (10)** → everything
- MVP = Phase 1–3 (US1)

### Within Each User Story

Tests ([TDD]) written and failing → geometry/services → routes → templates/JS → checkpoint. [REVIEW] tasks pause for human review. Story complete before the next priority starts (unless fanned out).

### Parallel Opportunities

- After Phase 2: **mapping track** (US1→US2→US3) and **onboarding track** (US4) share only the shell — parallelizable [SUBAGENT] (plan Execution Strategy)
- **US6 dashboard** and **US5 initiation** are read-heavy and independent — parallelizable with either track
- All [P] test-writing tasks within a phase can run together; T004 vendoring and T005 test scaffolding parallel to T003

---

## Superpowers Execution

### Execution Discipline by Marker

- **[TDD]**: RED-GREEN-REFACTOR via the `test-driven-development` skill if available — write test → run (must fail) → implement → run (must pass) → refactor. Applies to T006–T008, T011–T012, T014–T016, T023–T024, T027–T028, T031–T032, T038, T041.
- **[SUBAGENT]**: dispatch via `subagent-driven-development` if available; otherwise sequential. Candidate fan-out: US4 track vs US1–US3 track after Phase 2; T051.
- **[REVIEW]**: pause and present — T008 (auth middleware), T013 (CLI-body refactors). Additionally review contracts/http-routes.md's route↔code-path table before any handler work (plan Review Gate 1).
- **[P]**: parallel where files/dependencies allow.

### Checkpoint Protocol

At every phase boundary: summarize, run applicable tests (with AND without the studio group for anything touching core), report results, ask "Phase [N] complete. Proceed to Phase [N+1]?" — continue only on explicit approval. Phase-boundary checkpoints map to plan.md Human Checkpoints 1–5.

---

## Requirements Coverage Matrix

Every FR and SC from spec.md maps to at least one task (verified 2026-07-14 via writing-plans self-review; three gaps found and folded into T012/T022/T046).

| Requirement | Tasks | | Requirement | Tasks |
|---|---|---|---|---|
| FR-001 zero business logic | T012, T052, all route tasks | | FR-030/030a preview native+honest | T023, T025 |
| FR-002 cross-surface drafts | T012 (bidirectional) | | FR-031 approval gate parity | T024, T026 |
| FR-003 identical Transform | T024, T050 | | FR-032/032a spatial + multi-exemplar | T033, T035 |
| FR-004 no shadow state | T046 | | FR-033/033a review writes + region editing | T031, T032, T034, T036 |
| FR-005 conflict block | T011 | | FR-034 keyboard triage at scale | T031, T035, T036 |
| FR-006 terminal read-only | T020, T041 | | FR-035/035a verify report + prefill/next-step | T032, T034, T035, T037 |
| FR-010 full doc, lazy | T021 | | FR-036 session initiation | T038, T039, T040 |
| FR-011 anchored inventory + samples | T014, T017, T022 | | FR-037/037a onboarding initiation + drift shortcut | T038, T039, T040, T044 |
| FR-012 target rendering/panel | T019, T022 | | FR-038/039 dashboard, abandon, AI/consent | T041, T042, T043 |
| FR-013/013a/014/015 routes + tiers | T015, T017, T019, T020 | | FR-040/040a loopback + secret | T008, T009, T048 |
| FR-016 no name-overlap confidence | T022 | | FR-041 no auth machinery | T010 |
| FR-017 rail + dark chrome | T010 | | FR-042 deletability | T006, T007, T045 |
| FR-018 focus wires | T016, T020, T021 | | FR-043 no browser persistence | T018, T047 |
| FR-019 readiness = gate | T016, T020 | | FR-044 no AI where forbidden | T043, T046 |
| FR-020/021/022 link detail + valuemap + mechanisms | T027, T028, T029, T030 | | | |

| SC | Tasks | | SC | Tasks |
|---|---|---|---|---|
| SC-001 full journey | T050 | | SC-007 overlay coordinates | T014, T049 |
| SC-002 CLI-equal transform | T023, T024, T050 | | SC-008 triage < 30 min | T049 (measured at Checkpoint 4) |
| SC-003 loopback refusal | T008, T048 | | SC-009 unaided first attempt | T049 |
| SC-004 suite green w/o studio | T007, T045, T053 | | SC-010 < 5 s open, lazy nav | T021, T049 |
| SC-005 bidirectional finishability | T012 | | SC-011 secret/Host/Origin refusal | T008, T048 |
| SC-006 lifecycle audit | T046 | | | |

Edge cases: busy-DB retryable → T010; structureless diagnosis → T034; stale URL → T008/T048; racing approvals → T024; render problems verbatim → T023/T025; degraded AI → T038/T043; browser-close safety → server-side state by design + T046.

---

## Notes

- Total: **53 tasks** — Setup 5, Foundational 8, US1 9, US2 4, US3 4, US4 7, US5 3, US6 4, US7 4, Polish 5
- Every studio handler delegates to an existing code path (contracts/http-routes.md table is the enforcement surface); a handler containing business logic is a review-time defect (FR-001/D6)
- No new DB tables/migrations anywhere in this feature (data-model.md) — a task that seems to need one is a design breach; stop and flag in STATUS.md
- Dev/test exclusively on seed + synthetic fixtures (Constitution VII); the Eskom holdout is used read-only for geometry/triage verification
- Commit after each task or logical group, citing D6/D9/D11 where relied upon (Constitution IX)
