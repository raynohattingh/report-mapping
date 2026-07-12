# Data Model — Local AI Assistance Layer (002-local-ai-assist)

**Date**: 2026-07-11 · **Plan**: [plan.md](plan.md) · **Research**: [research.md](research.md)

Three surfaces change: one additive DB column, one new schema-validated config file, and richer JSON payloads inside already-existing session fields. The four append-only registries (SourceProfile, TargetTemplate, Transform, ValueMap) are untouched (Constitution III).

## 1. DB change (additive, Alembic)

### `mapping_sessions` — existing table, one new nullable column

| Column | Type | Notes |
|---|---|---|
| `assist_stats` | JSON, nullable | `NULL` = pre-002 session (rendered as "no assist metadata"). Written once at generation, updated only by explicit `map regenerate`. |

`assist_stats` payload:

```json
{
  "mode": "local",                       // none | local | external  (FR-013)
  "client": "demo",                       // per-session client id; required in external mode (FR-004)
  "generated_at": "2026-07-11T10:00:00+00:00",
  "assets": {
    "embedding": "fastembed:BAAI/bge-small-en-v1.5",
    "llm": "ollama:qwen3:4b"             // absent keys = tier unavailable/degraded (FR-011)
  },
  "degraded": ["llm"],                   // tiers that were unavailable or timed out
  "shown": 14,                            // proposals surfaced (FR-008 aggregate)
  "dropped": {"schema": 2, "unknown_field": 1, "unknown_value": 0, "timeout": 0},
  "superseded": []                        // prior generations moved here by `map regenerate` (FR-016)
}
```

**Mode values on `mapping_sessions.mode`**: existing column, values extended from `ai|manual` to `manual|local|external|stub` (`ai` remains valid on historical rows; new sessions write the new vocabulary; `manual` ≡ assist none; `--stub-ai` test sessions write `stub`). Data-only change, no migration needed for old rows. NOTE: `tests/integration/test_ai_session.py` asserts `mode == "ai"` today — that assertion is updated to `"stub"` as part of the CLI wiring task (it is an integration test, not part of the SC-004-protected invariant/golden suites).

### Persisted proposal entries — existing `mapping_sessions.proposals` JSON list

Each entry (today: `target_field, from_path, rationale, tier, value_map_name, suggested_entries, at`) gains:

| Key | Example | Purpose |
|---|---|---|
| `provider` | `"local"` | provenance per proposal (FR-013): `local` \| `external` \| `stub` |
| `asset` | `"ollama:qwen3:4b"` or `"fastembed:BAAI/bge-small-en-v1.5"` | which model produced it |

Review flow reads ONLY this persisted list (FR-016); providers are never re-consulted on `map review`/`map approve`.

### Candidate rankings — persisted inside `assist_stats.rankings`

```json
"rankings": {
  "priority": [
    {"target_field": "priority", "score": 0.81},
    {"target_field": "source_severity", "score": 0.74},
    {"target_field": "defect_code", "score": 0.41}
  ]
}
```

Keyed by source field; ordered lists (scores shown as "resembles", never confidence — Principle V). Shortlist length: min(5, schema size); deterministic tie-break = lexical on `target_field` (FR-012).

## 2. New config file — `<store>/ai.yaml` (schema: contracts/ai-config.schema.json)

```yaml
default_mode: local            # none | local | external
local:
  embedding_model: BAAI/bge-small-en-v1.5     # A12a
  llm_model: qwen3:4b                          # A12b; fallback documented: gemma3:4b
  ollama_host: "http://127.0.0.1:11434"        # MUST be loopback; validated (FR-002)
  timeout_seconds: 120                          # per-call; timeout => tier degrades (R10)
external:
  provider: anthropic
  model: claude-fable-5
consent:                        # owner-recorded, per client (FR-004); edited ONLY via `rmu ai consent`
  - client: demo
    granted_by: rayno
    granted_at: "2026-07-11"
    note: "demo data only"
```

Validation rules (enforced by `rmu/ai/config.py` against the JSON Schema + code checks):
- `ollama_host` must parse to a loopback host (`127.0.0.0/8`, `::1`, `localhost`) — anything else is a config error, refused at load (never silently ignored).
- `consent[].client` unique, non-empty; entries are appended/removed only by `rmu ai consent grant|revoke` (audit line printed on every change).
- Missing file ⇒ built-in defaults (mode `local`, no consent entries) — external mode therefore refuses until a grant exists.

**Mode resolution precedence** (R6): `--assist` CLI flag > `RMU_ASSIST_MODE` env > `ai.yaml default_mode` > `local`. `--no-ai` is a hard alias for `--assist none` (Constitution VII).

## 3. Key entities (spec ↔ implementation mapping)

| Spec entity | Implementation |
|---|---|
| Assistance Mode | resolved enum in `rmu/ai/config.py`; recorded on `mapping_sessions.mode` + `assist_stats.mode` |
| Consent Flag | `consent[]` entries in `ai.yaml`; checked at provider construction for external mode; matched against explicit `--client` |
| Candidate Ranking | `assist_stats.rankings` (persisted) rendered as shortlists in draft banner comments + review sheet |
| Proposal | existing `Proposal` dataclass + `provider`/`asset` provenance; persisted in `mapping_sessions.proposals` |
| Local Assistance Assets | probed by `rmu/ai/embeddings.py` (model cache present?) and `rmu/ai/llm_local.py` (loopback server up? model pulled?); reported by `rmu ai doctor` |
| Profile Fingerprint Similarity | computed on demand by `rmu profile suggest`; NOT persisted (suggestions are ephemeral session output; the analyst's registration action is the durable artifact) |

## 4. State transitions

```
map start --assist local
  ├─ resolve mode ─ probe assets ─ per-tier availability (FR-011)
  ├─ generate: rank fields (tier 1) → propose value maps (tier 2, optional)
  ├─ gate: schema validate → referent resolve → drop+count (FR-008)
  └─ persist ONCE: proposals(+provenance) + assist_stats(+rankings)   [FR-016]

map review / map approve
  └─ read persisted set only; approve path unchanged (T2 blocks approval as today)

map regenerate --session N   (explicit analyst action, FR-016)
  ├─ move current {proposals, stats} → assist_stats.superseded[]
  └─ re-run generate+gate+persist; prints old/new diff summary

external mode start
  └─ require --client → consent lookup → missing ⇒ exit(4) with explanation (SC-005); granted ⇒ AnthropicProvider
```

## 5. Invariants preserved (checked by tests)

- Same `Proposal` dataclass feeds `build_draft()` in every mode ⇒ draft YAML, transform YAML, lineage, decision log are structurally identical across modes (FR-009, SC-006).
- No import path from `rmu/{apply,detect,extract,validate,render}` to `rmu.ai` or `rmu.mapping.providers` (extended `test_no_ai_in_apply`).
- Registry tables untouched; `assist_stats` migration is additive with `NULL` default (Constitution III).
