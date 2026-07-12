# Tasks: Local AI Assistance Layer

**Input**: Design documents from `/specs/002-local-ai-assist/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (all present)

**Tests**: INCLUDED — the spec's acceptance criteria are themselves tests (SC-001…SC-008), and Constitution VIII mandates test-first on invariant-grade claims. [TDD] tasks: write the test, watch it fail, then implement.

**Organization**: Grouped by user story from spec.md. US1 (P1) is the MVP; US2/US4 (P2) next; US3 (P3) last.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on an incomplete task)
- **[TDD]**: test written and failing before implementation
- **[REVIEW]**: pause for human review
- Story labels [US1]–[US4] map to spec.md user stories

## Cross-Task Interface Contracts

A task's implementer sees only their own task — these are the signatures neighboring tasks rely on (writing-plans discipline; keep names exact):

- `rmu.ai.config`: `load_ai_config(store_root: Path) -> AiConfig` (raises `AiConfigError` on non-loopback host); `resolve_mode(flag: str | None, env: str | None, cfg: AiConfig) -> str`; `has_consent(cfg: AiConfig, client: str) -> bool`; `grant_consent(...)/revoke_consent(...)` (T007 → consumed by T010, T013, T023, T024, T025)
- `rmu.ai.embeddings`: `EmbeddingBackend.available() -> bool`; `EmbeddingBackend.embed(texts: list[str]) -> list[list[float]]` — cache-only, never downloads (T008 → consumed by T015, T019, T021)
- `rmu.ai.llm_local`: `LocalLLM.available() -> bool`; `LocalLLM.complete_json(prompt: str) -> str | None` (None on timeout/unavailable) (T013 → consumed by T015, T027)
- `rmu.ai.validation`: `gate_proposals(raw_json: str, *, source_inventory: dict, target_fields: set[str], observed_values: dict[str, set[str]]) -> tuple[list[Proposal], dict[str, int]]` — second element is dropped-by-reason (T014 → consumed by T015, T028)
- `rmu.ai.ranking`: `rank_candidates(source_fields: dict[str, str], target_fields: dict[str, str], backend) -> dict[str, list[dict]]` returning `{source_field: [{"target_field", "score"}, …]}` shortlists (T019 → consumed by T015, T020)
- `rmu.mapping.providers`: `get_provider(mode: str, *, stub: bool = False, client: str | None = None, config: AiConfig) -> ProposalProvider`; `LocalProvider.propose(...)` keeps the existing `ProposalProvider` protocol signature — the `Proposal` dataclass is unchanged except optional provenance attrs (T010/T015 → consumed by T016, T022, T023)
- Persisted shapes: `assist_stats` payload and per-proposal `provider`/`asset` keys exactly as data-model.md §1 (T016 → consumed by T017, T020, T028)

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: dependencies + data files the whole feature builds on

- [x] T001 Add `fastembed>=0.5` and `ollama>=0.4` to `pyproject.toml` dependencies (A12a/A12b), run `uv lock && uv sync`, verify imports
- [x] T002 [P] [SUBAGENT] Install proposal gate schema as data: copy `specs/002-local-ai-assist/contracts/proposal.schema.json` to `src/rmu/mapping/schemas/proposal.schema.json` (Constitution IV)
- [x] T003 [P] [SUBAGENT] Install ai-config schema as data: copy `specs/002-local-ai-assist/contracts/ai-config.schema.json` to `src/rmu/ai/schemas/ai_config.schema.json` (create `src/rmu/ai/` + `src/rmu/ai/__init__.py` + `src/rmu/ai/schemas/`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: test fixtures, config core, provider seam refactor — everything every story needs

**CRITICAL**: No user story work can begin until this phase is complete.

- [x] T004 [P] [SUBAGENT] [TDD] Add `block_non_loopback_network` pytest fixture in `tests/conftest.py`: patch `socket.socket.connect`/`socket.create_connection`/`socket.getaddrinfo` to raise on any non-loopback, non-AF_UNIX address (research R3); self-test that loopback passes and an external connect raises
- [x] T005 [P] [SUBAGENT] Build fake loopback Ollama stub in `tests/fixtures/fake_ollama.py`: stdlib `http.server` on `127.0.0.1:<free port>` serving `/api/chat` (canned temp-0 JSON bodies) and `/api/tags` (research R3)
- [x] T006 [P] [SUBAGENT] Extend import ban in `tests/invariants/test_no_ai_in_apply.py`: `rmu.ai` joins `rmu.mapping.providers` as forbidden imports for `rmu/{apply,detect,extract,validate,render}` (Constitution II/VI); existing assertions unchanged
- [x] T007 [TDD] Implement `src/rmu/ai/config.py`: load/schema-validate `<store>/ai.yaml`, built-in defaults when absent, mode resolution precedence (flag > `RMU_ASSIST_MODE` > file > `local`), loopback-host validation (refuse non-loopback `ollama_host` at load), consent lookup/grant/revoke API (data-model §2, research R6) — unit tests first in `tests/unit/test_ai_config.py`
- [x] T008 [P] [SUBAGENT] Implement `src/rmu/ai/embeddings.py`: lazy fastembed wrapper — availability probe (cache present? import ok?), embed-batch API, **cache-only**: never downloads at session time, absent cache reports unavailable (FR-011/FR-014, research R1)
- [x] T009 Additive Alembic migration + model change: nullable `assist_stats` JSON column on `mapping_sessions` in `src/rmu/models.py` and `alembic/versions/` (data-model §1; NOT an append-only registry table — Constitution III safe)
- [x] T010 [REVIEW] Refactor provider construction in `src/rmu/mapping/providers.py`: `get_provider(mode: str, *, stub: bool, client: str | None, config)` replaces `get_provider(no_ai, stub)`; `none`→NullProvider, `stub` kept for tests, `external`→AnthropicProvider (consent gate lands in T023); update call sites in `src/rmu/cli.py` with `--no-ai` behavior preserved; ALL existing tests must stay green before proceeding

**Checkpoint**: fixtures prove loopback semantics, config core tested, seam refactored with zero behavior change.

---

## Phase 3: User Story 1 — Provably Offline Mapping Assistance (Priority: P1) 🎯 MVP

**Goal**: full mapping session in `local` mode produces schema-gated, persisted, provenance-tagged proposals with zero non-loopback network I/O.

**Independent Test**: `uv run pytest tests/integration/test_local_session_offline.py` — complete `map start --assist local` under the socket-blocking fixture succeeds with proposals present (SC-001).

### Tests for User Story 1

- [x] T011 [P] [TDD] [US1] Write `tests/integration/test_local_session_offline.py`: bootstrap DB+seed, run `map start --assist local` on `seed/source_samples/Distribution-report.pdf` under `block_non_loopback_network` + `fake_ollama`; assert exit 0, T2 proposals with rationale persisted, `assist_stats.mode == "local"`, shown/dropped counts present (SC-001, FR-002/013). ALSO cover per-tier degradation (FR-011, clarification 1): embeddings-only (fake Ollama down) ⇒ rankings present, no value-map proposals, `assist_stats.degraded == ["llm"]`, exit 0; no assets at all ⇒ manual session, clear stderr message, exit 0
- [x] T012 [P] [SUBAGENT] [TDD] [US1] Write `tests/unit/test_proposal_gate.py`: schema-invalid JSON dropped; schema-valid but unknown `target_field`/`from_path`/unobserved `source_value` dropped; drop reasons counted per category; valid proposals pass untouched (SC-003, FR-008)

### Implementation for User Story 1

- [x] T013 [US1] Implement `src/rmu/ai/llm_local.py`: Ollama client hard-pinned to loopback (validates host, refuses otherwise), `temperature 0`, `format json`, per-call timeout from config (default 120s), availability probe (server up? model pulled? **runtime bound to localhost only** — treat a non-loopback `OLLAMA_HOST`/advertised binding as unavailable with an explanatory message, FR-002/analysis C1), timeout ⇒ unavailable-shaped result (research R2/R10)
- [x] T014 [US1] Implement `src/rmu/ai/validation.py`: jsonschema gate against `src/rmu/mapping/schemas/proposal.schema.json` + referent resolution against source inventory/template schema/observed values + drop accounting `{reason: count}` (research R4) — makes T012 pass
- [x] T015 [US1] Implement `LocalProvider` in `src/rmu/mapping/providers.py`: composes embeddings probe + optional LLM proposals through the validation gate; per-tier degradation with clear stderr messages (embeddings-only ⇒ no value-map proposals; nothing ⇒ manual, exit 0) (FR-011, clarification 1)
- [x] T016 [US1] Wire session persistence + CLI in `src/rmu/mapping/session.py` and `src/rmu/cli.py`: `map start --assist/--client` flags, provenance keys (`provider`, `asset`) on each persisted proposal, write `assist_stats` (mode, client, assets, degraded, shown, dropped, generated_at), progress lines on stderr, `assist: <mode> shown=<n> dropped=<m>` summary (FR-013/016, SC-008, contracts/cli-ai.md); new sessions write mode vocabulary `manual|local|external|stub` (`--stub-ai` ⇒ `stub`) and update the `ms.mode == "ai"` assertion in `tests/integration/test_ai_session.py` accordingly (analysis I1 — integration test, outside the SC-004 protected suites) — makes T011 pass
- [x] T017 [US1] Implement `rmu map regenerate --session <id>` in `src/rmu/cli.py`: move current proposals+stats to `assist_stats.superseded[]`, re-generate+gate+persist, print superseded summary, exit 3 on approved sessions; integration test `tests/integration/test_regenerate.py` (FR-016)

**Checkpoint**: MVP — offline assisted session provable by test. Get human approval.

---

## Phase 4: User Story 2 — Ranked Candidate Target Fields (Priority: P2)

**Goal**: per-source-field shortlists ranked by semantic similarity; ≥90% top-3 on seed ground truth; session-side profile-fingerprint suggestions.

**Independent Test**: `uv run pytest tests/unit/test_ranking.py tests/unit/test_fingerprint_similarity.py` — top-3 hit rate ≥90% on `tests/fixtures/ranking_ground_truth.yaml`; rankings deterministic across runs.

### Tests for User Story 2

- [x] T018 [P] [SUBAGENT] [TDD] [US2] Build ground truth `tests/fixtures/ranking_ground_truth.yaml` from the human-confirmed routes in `examples/transform.annexc_pack.yaml` and `examples/transform.defect_csv.yaml` (one profile, two interim templates — research R5, analysis A1); the YAML declares its expected route count N so the eval reports `x/N` alongside the percentage (small-N caveat in the test docstring, analysis U1). Write `tests/unit/test_ranking.py`: top-3 ≥90% (SC-002), identical ordering across two runs, lexical tie-break (FR-012); skip cleanly when embedding cache absent (the T031 gate requires a non-skipped run before done)

### Implementation for User Story 2

- [x] T019 [US2] Implement `src/rmu/ai/ranking.py`: field descriptors (name + template schema label + sample values), cosine ranking, shortlist length min(5, schema size), deterministic lexical tie-break, "resembles" score payload (FR-005/012, Principle V) — makes T018 pass
- [x] T020 [US2] Surface shortlists: persist `assist_stats.rankings` in `src/rmu/mapping/session.py`, render ranked shortlist per T3/unmapped field in draft banner comments and in `src/rmu/mapping/review_sheet.py` (no confidence language) (data-model §1)
- [x] T021 [P] [SUBAGENT] [US2] Implement `src/rmu/ai/fingerprint_similarity.py` + `rmu profile suggest <pdf>` in `src/rmu/cli.py`: embed structural signals via existing pdfplumber path (read-only reuse, `detect/fingerprint.py` unmodified), rank registered profiles, "resembles X (score)" output, exit 5 without tier-1 assets; unit test `tests/unit/test_fingerprint_similarity.py` (FR-015, research R7)

**Checkpoint**: ranking measured against ground truth; US1 still passes.

---

## Phase 5: User Story 4 — Owner-Controlled Assistance Modes (Priority: P2)

**Goal**: `none`/`local`/`external` switchable in config; external hard-gated on per-client recorded consent; artifacts identical across modes.

**Independent Test**: `uv run pytest tests/integration/test_assist_modes.py` — external-without-consent exits 4 (SC-005); `--assist none` session fully functional with structurally identical artifacts (SC-006).

### Tests for User Story 4

- [x] T022 [P] [TDD] [US4] Write `tests/integration/test_assist_modes.py`: external without `--client` ⇒ exit 4; external with `--client` but no consent entry ⇒ exit 4 + explanatory message; consent for client A does not authorize client B; `--assist none` and `--no-ai` alias run end to end; approved-transform YAML keys and session artifact shapes identical across `none`/`stub` modes (SC-005/006, FR-003/004/009)

### Implementation for User Story 4

- [x] T023 [US4] Consent gate in `src/rmu/mapping/providers.py` + `src/rmu/cli.py`: external mode requires `--client` + matching `ai.yaml` consent entry (via T007 API), refusal exit 4 with grant instructions; client id recorded on session; `--no-ai` alias for `--assist none` (FR-004, contracts/cli-ai.md) — makes T022 pass
- [x] T024 [P] [SUBAGENT] [US4] Implement `rmu ai consent grant|revoke|list` subcommands in `src/rmu/cli.py` (only writers of the consent block, audit line per change) per contracts/cli-ai.md
- [x] T025 [P] [SUBAGENT] [US4] Implement `src/rmu/ai/doctor.py` + `rmu ai doctor` (per-tier health: embedding cache, ollama loopback-bound + model pulled, consent summary; `--json` output) and `rmu ai setup` (prints manual install steps, downloads nothing) (FR-014, quickstart.md)

**Checkpoint**: mode matrix provable; consent is the only path off the machine.

---

## Phase 6: User Story 3 — Local ValueMap Proposals with Rationales (Priority: P3)

**Goal**: locally produced ValueMap entries with one-line rationales land in the unchanged review flow; aggregate drop counts visible.

**Independent Test**: `uv run pytest tests/integration/test_local_valuemap_proposals.py` — value-map proposals arrive as T2 + starter files with rationales, registry untouched until human `valuemap create`, review sheet shows shown/dropped banner.

### Tests for User Story 3

- [x] T026 [P] [SUBAGENT] [TDD] [US3] Write `tests/integration/test_local_valuemap_proposals.py` (fake Ollama): severity/issue vocabularies produce ValueMap proposals with non-empty one-line rationales; starter files emitted; `valuemap list` empty until human creates; a canned malformed response increments the dropped count shown on the review sheet (US3 scenarios, FR-006/007/008)

### Implementation for User Story 3

- [x] T027 [US3] Value-map proposal prompts in `src/rmu/ai/llm_local.py`/`LocalProvider`: compact per-vocabulary prompts (observed source values + target vocabulary from template schema/defect codes), rationale required by the gate (FR-006) — makes T026's proposal assertions pass
- [x] T028 [US3] Aggregate assist banner in `src/rmu/mapping/review_sheet.py`: always render `shown`/`dropped`-by-reason from `assist_stats` (also when 0 dropped); degraded tiers noted (FR-008, clarification/brainstorm)

**Checkpoint**: all four stories independently green.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T029 [P] [SUBAGENT] Documentation: local-AI setup + mode/consent section in `README.md` sourced from `specs/002-local-ai-assist/quickstart.md`; cite A9/A12a/A12b/D8 (FR-014)
- [x] T030 [P] [SUBAGENT] Optional perf smoke test `tests/integration/test_assist_perf.py` marked `slow`: whole-exemplar generation ≤5 min against real local assets, auto-skip when assets absent (SC-008, research R10)
- [x] T031 Full-suite gate: `uv run pytest` — entire suite green with `tests/invariants/` and golden files **unmodified** except the T006 import-ban extension (SC-004); `uv run ruff check src tests` clean. SC-002 must be MEASURED, not skipped: run `uv run pytest tests/unit/test_ranking.py -v` on the A9 machine with the embedding cache installed and confirm the eval executed (a skip does not satisfy the gate — analysis G1)
- [x] T032 [REVIEW] Update `STATUS.md` (session log: done/decisions/next/open questions, CLAUDE.md rule 8) and confirm ASSUMPTIONS.md A12a/A12b entries match what was actually installed

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: none — start immediately; T002/T003 parallel after T001
- **Phase 2 (Foundational)**: needs Phase 1; T004/T005/T006/T008 parallel; T007 before T010 (config feeds provider construction); T009 independent; T010 [REVIEW] last — BLOCKS all stories
- **Phase 3 (US1/P1, MVP)**: needs Phase 2; T011/T012 (tests) first; T013→T014→T015→T016→T017
- **Phase 4 (US2/P2)**: needs Phase 2 (+T008); independent of US1 except T020 touches session.py after T016 — run Phase 4 after Phase 3 or coordinate the file
- **Phase 5 (US4/P2)**: needs Phase 2 (T007/T010); T022 first; T024/T25 parallel with T023
- **Phase 6 (US3/P3)**: needs US1 (LLM path + gate)
- **Phase 7 (Polish)**: needs all desired stories

### Parallel Opportunities

- Phase 2: T004, T005, T006, T008 simultaneously (4 different files)
- Phase 3: T011 ∥ T012 (test authoring)
- Phase 5: T024 ∥ T025 while T023 proceeds
- Phase 7: T029 ∥ T030

## Implementation Strategy

**MVP first**: Phases 1–3 alone deliver the headline claim (provably offline assisted session) — demoable with Wi-Fi off. Then US2 (ranking = the biggest time-saver), US4 (safety/compliance gate), US3 (value-map depth), polish. Stop-line under time pressure (D3-consistent): everything after Phase 3 degrades gracefully because the manual path and per-tier degradation are already in the MVP.

## Superpowers Execution

### Execution Discipline by Marker

- **[TDD]**: RED-GREEN-REFACTOR; use the `test-driven-development` skill if available
- **[REVIEW]**: pause, present, wait for explicit approval (T010 seam refactor, T032 close-out)
- **[P]**: parallel-safe within its phase

### Checkpoint Protocol

At each phase boundary: summarize, run that story's independent test + `tests/invariants/`, report, and ask before proceeding.
