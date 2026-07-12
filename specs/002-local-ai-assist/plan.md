# Implementation Plan: Local AI Assistance Layer

**Branch**: `002-local-ai-assist` | **Date**: 2026-07-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-local-ai-assist/spec.md`

## Summary

Give the HIL mapping session AI proposals that provably never leave the machine: a three-mode assistance layer (`none` | `local` default | `external` consent-gated) behind the existing `ProposalProvider` seam. Tier 1 is in-process CPU embeddings (fastembed + bge-small-en-v1.5, A12a) for ranked candidate target fields and session-side profile-fingerprint similarity; tier 2 is an optional loopback-pinned Ollama LLM (qwen3:4b, A12b, temp 0, JSON-constrained) for value-map proposals with rationales. Every proposal is schema-validated then referent-resolved (drops counted and shown in aggregate), persisted once per session with provenance, and enters the unchanged review flow at tier T2. Apply/validate/render/audit are untouched in every mode; the guarantee is enforced by a non-loopback socket-blocking test fixture. Full technology decisions: [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12 (fixed by constitution)

**Primary Dependencies**: existing stack + `fastembed>=0.5` (in-process ONNX embeddings, A12a), `ollama>=0.4` (loopback client, A12b); `jsonschema` (already present) for the proposal gate; `anthropic` unchanged for the external tier

**Storage**: SQLite via SQLAlchemy/Alembic (existing). Additive-only change: nullable `assist_stats` JSON column on `mapping_sessions` (not an append-only registry table). New file-based config `<store>/ai.yaml` (modes, model names, consent entries), schema-validated

**Testing**: pytest — new socket-blocking fixture (loopback-only), ranking-accuracy eval on bundled fixtures (SC-002 ≥90% top-3), proposal-drop tests, consent-refusal tests, fake loopback Ollama (stdlib) for CI; existing invariant/golden/determinism suites must pass **unmodified** (SC-004)

**Target Platform**: macOS Apple-silicon, CPU-only, ≥16GB (A9 reference machine); no GPU dependency

**Project Type**: single project — CLI tool (`rmu`), new `src/rmu/ai/` package + extensions to `src/rmu/mapping/`

**Performance Goals**: whole-exemplar assistance ≤5 min on A9 as one visible step with progress (SC-008); ranking lookups instant (<1s); per-call timeout (default 120s) degrades a slow tier like an absent one

**Constraints**: zero non-loopback network I/O in local mode (loopback to a localhost-bound runtime only); `none` mode fully functional (D3 floor); no AI at apply time ever; no model auto-download at session time (manual documented setup, FR-014); artifact formats identical across modes

**Scale/Scope**: single operator (A5); two seed exemplars × two interim templates as eval corpus; target schemas of ~10–30 fields; value vocabularies of ≤ ~50 observed values

## Constitution Check

*GATE: evaluated against constitution v1.0.0 before Phase 0; re-checked after Phase 1.*

| # | Principle | Verdict | How this plan complies |
|---|---|---|---|
| I | TBD discipline | PASS | Feature touches only the two INTERIM templates as ranking targets; no Annexure-H/SAP content invented — target-field descriptors come from registry `required_schema` data. |
| II | Deterministic apply | PASS | All new code lives in the mapping session (`rmu/ai/`, `rmu/mapping/providers.py`); apply/validate/render/audit unchanged; existing determinism + `test_no_ai_in_apply` suites run unmodified (SC-004), with the import ban extended to `rmu.ai`. |
| III | Append-only registries | PASS | No change to the four registry tables. `mapping_sessions` (not registry) gains one nullable JSON column via additive Alembic migration; old rows stay valid (`NULL` = pre-002 session). |
| IV | Templates/transforms are data | PASS | Model names, hosts, timeouts, mode default = data in `ai.yaml` (schema-validated); proposal gate = JSON Schema file; no pipeline code knows model names. |
| V | No false confidence | PASS | Rankings are shortlists with "resembles" wording, never match verdicts; proposals enter at T2 exactly as today (approval-blocked); drop counts always shown; SafeCard logic untouched. |
| VI | Decoupled stages | PASS | `rmu.ai` is used only by mapping-session code and new session-side CLI commands; `detect/fingerprint.py` unmodified — fingerprint similarity reads registry rows, apply-time detection unchanged. |
| VII | Data sensitivity + `--no-ai` | PASS | This feature is the structural fix: local tier keeps data on-machine; external tier hard-gated on per-client recorded consent; `--no-ai` kept as alias of `--assist none` and remains fully functional; all tests use seed/synthetic data. |
| VIII | Test-first on invariants | PASS | New invariant-grade tests written first: non-loopback socket block (SC-001), consent refusal (SC-005), malformed-drop (SC-003), mode-artifact-equivalence (SC-006/FR-009); existing invariant tests untouched. |
| IX | Assumption traceability | PASS | A12a/A12b recorded in ASSUMPTIONS.md at plan time; code/commits cite A9, A12a/b, D5, D8. |

**Post-Phase-1 re-check (2026-07-11)**: design artifacts (data-model.md, contracts/) introduce no registry mutations, no apply-time AI, no new pipeline coupling — verdicts unchanged, gate PASS. No Complexity Tracking entries required.

## Project Structure

### Documentation (this feature)

```text
specs/002-local-ai-assist/
├── plan.md              # This file
├── research.md          # Phase 0 (R1–R10: models, fixture, config, eval)
├── data-model.md        # Phase 1 — config entities, session additions, proposal shape
├── quickstart.md        # Phase 1 — manual asset setup + offline demo walkthrough
├── contracts/           # Phase 1
│   ├── proposal.schema.json   # strict gate for model outputs (FR-008)
│   ├── ai-config.schema.json  # ai.yaml: modes, models, consent entries
│   └── cli-ai.md              # CLI contract: rmu ai *, map start --assist/--client, profile suggest, map regenerate
└── tasks.md             # Phase 2 (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/rmu/
├── ai/                          # NEW package — everything model-shaped lives here
│   ├── __init__.py
│   ├── config.py                # ai.yaml load/validate, mode resolution, consent checks (R6)
│   ├── embeddings.py            # fastembed wrapper: lazy import, cache-only, availability probe (R1)
│   ├── ranking.py               # field descriptors + cosine ranking + deterministic tie-break (R5)
│   ├── llm_local.py             # Ollama client: loopback-pinned, temp 0, format json, timeout (R2)
│   ├── validation.py            # proposal schema + referent resolution + drop accounting (R4)
│   ├── fingerprint_similarity.py# session-side profile suggestions (R7, FR-015)
│   └── doctor.py                # asset/runtime health for `rmu ai doctor`
├── mapping/
│   ├── providers.py             # + LocalProvider, consent-gated external path, get_provider(mode)
│   ├── session.py               # + provenance keys on persisted proposals, assist stats
│   ├── review_sheet.py          # + shown/dropped counts + shortlist rendering
│   └── schemas/
│       └── proposal.schema.json # the FR-008 gate (data, not code)
├── models.py                    # + MappingSession.assist_stats (nullable JSON)
└── cli.py                       # + ai_app (doctor, consent, setup), map start --assist/--client,
                                 #   map regenerate, profile suggest

alembic/versions/                # + additive migration: mapping_sessions.assist_stats

tests/
├── conftest.py                  # + block_non_loopback_network fixture (R3)
├── fixtures/
│   ├── ranking_ground_truth.yaml# confirmed routes eval set (R5)
│   └── fake_ollama.py           # stdlib loopback stub server for CI (R3)
├── invariants/
│   └── test_no_ai_in_apply.py   # extended: rmu.ai joins the import ban (unchanged assertions otherwise)
├── integration/
│   ├── test_local_session_offline.py   # SC-001 socket-blocked full session
│   ├── test_assist_modes.py            # SC-005 consent refusal, SC-006 mode equivalence, --no-ai alias
│   └── test_regenerate.py              # FR-016 persistence + explicit regeneration
└── unit/
    ├── test_ai_config.py        # mode precedence, consent registry, ai.yaml schema
    ├── test_ranking.py          # SC-002 top-3 eval + determinism/tie-break
    ├── test_proposal_gate.py    # SC-003 malformed/unresolvable drops + counts
    └── test_fingerprint_similarity.py
```

**Structure Decision**: single-project layout preserved. One new package (`rmu/ai/`) isolates model concerns behind the existing `ProposalProvider` seam in `rmu/mapping/providers.py` — the only file where modes meet the session. Pipeline stage packages (`apply/`, `detect/`, `extract/`, `validate/`, `render/`) are not touched, keeping Principle VI mechanical to verify.

## Complexity Tracking

No constitution violations — table intentionally empty.
