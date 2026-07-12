# Research — Local AI Assistance Layer (002-local-ai-assist)

**Date**: 2026-07-11 · **Spec**: [spec.md](spec.md) · Resolves all Technical Context unknowns.

## R1 — Tier-1 embedding stack (A12a)

**Decision**: `fastembed` (Apache-2.0, Qdrant) running `BAAI/bge-small-en-v1.5` (MIT, 384-dim, ~130MB ONNX) fully **in-process** on CPU.

**Rationale**:
- In-process ONNX inference means tier 1 uses **zero sockets of any kind** — stronger than the loopback allowance the spec grants, and it keeps per-tier degradation clean: ranking works even when no model runtime (Ollama) is installed at all (FR-011).
- No PyTorch dependency (~2GB avoided); `fastembed` pulls only `onnxruntime` + `tokenizers`, acceptable for a uv-managed CLI tool.
- Deterministic on same machine + same model files (FR-012): ONNX CPU EP is run-to-run stable; ties broken lexically by target field name in our code.
- bge-small-en-v1.5 is a retrieval-tuned model appropriate for short field-name/description strings; 2026 surveys still list the MiniLM/BGE-small class as the CPU speed/quality sweet spot.
- Model files are fetched once by a **documented manual step** (`rmu ai setup` prints instructions; `fastembed` caches locally) — no silent downloads at session time (FR-014): the provider refuses to download and degrades instead if the cache is absent.

**Alternatives considered**:
- `sentence-transformers` + all-MiniLM-L6-v2: fine quality, but drags in torch; rejected on dependency weight (A9 personal machine, uv env).
- Ollama embeddings (nomic-embed-text): one runtime for both tiers, but makes tier 1 depend on Ollama being installed and serving — weakens the degradation ladder and the zero-socket property of ranking. Rejected.
- Static-embedding models (e.g. potion/model2vec): fastest, but measurably weaker semantics for the "Severity ≈ Priority/Urgency" association the spec's SC-002 demands. Rejected for v1; config-swappable later (D8: tiers are config).

## R2 — Tier-2 local LLM (A12b)

**Decision**: **Ollama** runtime serving **`qwen3:4b`** (Apache-2.0), called with `temperature 0`, `format: "json"` (Ollama structured-output mode), over its loopback HTTP API. **Implementation note (build-time revision):** the client is the Python **stdlib `urllib`** hitting an explicit loopback URL, not the `ollama` package — one fewer dependency, and the loopback pin becomes enforceable in our own code (we construct/validate the URL). The `ollama` package was therefore NOT added. Same wire protocol, so real Ollama and the stdlib fake server (research R3) are exercised identically.

**Rationale**:
- D8 names Ollama; A9 sizes the model at ≤~4B params for a CPU-only ≥16GB Apple-silicon machine. Qwen3-4B is Apache-2.0 (no research-license trap like Qwen2.5-3B), strong at short structured-JSON tasks, and comfortably in budget (~3GB quantized).
- Ollama's `format` parameter constrains decoding to valid JSON, cutting the malformed-output rate before our jsonschema gate (FR-008) even runs.
- Loopback guarantee (FR-002): the provider hard-codes/validates the host — refuses to construct against any non-loopback `OLLAMA_HOST`, and `rmu ai doctor` verifies the server is bound to localhost.
- Fallback candidate (documented in config comments, not code): `gemma3:4b` (Apache-2.0-style Gemma terms, best RAM efficiency per 2026 comparisons). Swap is config-only (D8).

**Alternatives considered**:
- `llama-cpp-python` in-process: zero sockets, but heavier build/install friction on macOS, GGUF management by hand, and D8 explicitly names Ollama. Rejected for v1.
- `llama3.2:3b`: Llama community license (attribution/branding obligations) and higher observed RAM in comparisons; Apache-2.0 preferred. Rejected.
- Bigger models (7–8B): better proposals but threaten SC-008's ≤5-min budget on CPU and A9's memory envelope. Rejected; config-swappable.

## R3 — Zero-network test fixture

**Decision**: A pytest fixture (`tests/conftest.py`: `block_non_loopback_network`) that monkeypatches `socket.socket.connect` (and `create_connection`) to raise `AssertionError` for any address that is not loopback (`127.0.0.0/8`, `::1`) or `AF_UNIX`. DNS resolution (`getaddrinfo`) for non-local names is also blocked, so a stray HTTPS call fails fast even before connect.

**Rationale**: Connect-level interception catches every client library (httpx, urllib, anthropic SDK) without caring how it creates sockets; allowing loopback matches the clarified guarantee ("no data leaves the machine") and lets a live local Ollama be exercised where present. In CI/offline runs, tier-2 tests use a **fake loopback Ollama** (stdlib `http.server` on 127.0.0.1) serving canned temp-0 responses, so the socket-blocked session test never needs the real runtime.

**Alternatives considered**: `pytest-socket` plugin (adds a dep for what is ~20 lines and needs its loopback allowance configured anyway — rejected); OS-level firewalling (not portable, not CI-friendly — rejected).

## R4 — Proposal validation gate

**Decision**: JSON Schema (Draft 2020-12) at `src/rmu/mapping/schemas/proposal.schema.json` validated with the existing `jsonschema` dep, followed by a **resolution check** against session context: `from_path` must exist in the exemplar's source inventory, `target_field` in the template's `required_schema` (or known optional fields), `value_map` source values in the observed value set. Failures are dropped, counted per reason, and the counts land in the session record + review sheet header (FR-008).

**Rationale**: Schema-valid-but-unresolvable is the spec's own edge case; two-stage validation (shape, then referents) keeps "semantically absurd" outputs out without any trust in the model. Mirrors the transform-YAML schema-validation convention already in the repo (Constitution IV).

## R5 — Ranking ground truth & eval (SC-002)

**Decision**: Ground truth = the human-confirmed routes in the two committed example transforms `examples/transform.annexc_pack.yaml` and `examples/transform.defect_csv.yaml` (one source profile — both seed PDFs share it — × two interim templates), expressed as a small YAML eval file `tests/fixtures/ranking_ground_truth.yaml` (`source_field → confirmed target_field` per template, with the expected route count N declared so the eval reports x/N). A pytest test embeds source-field descriptors (name + sample values) and target-field descriptors (name + schema label), ranks, and asserts top-3 hit rate ≥ 90% overall.

**Rationale**: Uses only bundled demo data (Constitution VII); the confirmed routes already exist from the M3 worked example, so the metric is measured, not aspirational. Sample values are included in the embedded text because field names alone ("Id") under-determine matches — value context is what makes "1–5/?" rank near "Priority".

## R6 — Assistance modes, config surface & consent registry

**Decision**:
- Mode precedence: CLI flag (`--assist none|local|external`) > env `RMU_ASSIST_MODE` > config file default > built-in default `local`. The existing `--no-ai` flag is kept as an alias for `--assist none` (Constitution VII wording).
- Config file: `<store>/ai.yaml` (schema-validated), holding `default_mode`, model names/hosts per tier, and `consent:` — a list of `{client, granted_by, granted_at, note}` entries.
- Consent is edited **only** via explicit owner commands `rmu ai consent grant|revoke|list --client <id>`; external sessions require `--client <id>` and a matching entry, else exit non-zero with an explanatory message (FR-004). `map start` records the client id and mode on the session.

**Rationale**: File-based config matches the repo's data-not-code stance and keeps consent out of the append-only registries (it is operational state, not a mapping artifact). Explicit grant command satisfies "deliberate, owner-recorded; no in-session prompt can create it".

**Alternatives considered**: consent as a DB table (overkill for single-operator A5; harder to eyeball/audit than a YAML file — rejected); global boolean consent (fails the per-client clarification — rejected).

## R7 — Profile-fingerprint similarity (FR-015)

**Decision**: New session-side command `rmu profile suggest <pdf>`: extract the document's structural signals (leading-page text anchors, detected table header row, header keys) with the existing pdfplumber path, embed a canonicalized fingerprint string, compare (cosine) against embeddings of each registered profile's fingerprint (+ its anchors), print a ranked list with scores labeled as **suggestions**. Apply-time `detect_profile` is untouched.

**Rationale**: Reuses `detect/fingerprint.py`'s notion of structural signals without modifying it (Principle VI — the AI module reads registry rows, it does not reach into Detect). Output wording avoids confidence language (Principle V): scores are shown as "resembles", never as a match verdict.

## R8 — Provider architecture

**Decision**: Keep the existing `ProposalProvider` protocol in `rmu/mapping/providers.py` as the session-facing seam; add a new package `src/rmu/ai/` owning everything model-shaped:

- `rmu/ai/config.py` — load/validate `ai.yaml`, mode resolution, consent checks
- `rmu/ai/embeddings.py` — fastembed wrapper (lazy import, cache-only, availability probe)
- `rmu/ai/ranking.py` — field descriptor building + cosine ranking + deterministic tie-break
- `rmu/ai/llm_local.py` — Ollama client (loopback-pinned, temp 0, format json, availability probe)
- `rmu/ai/validation.py` — proposal schema + referent resolution + drop accounting
- `rmu/ai/fingerprint_similarity.py` — R7
- `rmu/ai/doctor.py` — asset/runtime health report backing `rmu ai doctor`
- `rmu/mapping/providers.py` gains `LocalProvider` (composes ranking + optional LLM proposals, per-tier degradation) and a consent-gated construction path for `AnthropicProvider`; `get_provider(mode, ...)` replaces `get_provider(no_ai, stub)` (stub retained for tests).

**Rationale**: The no-AI-in-apply invariant test already forbids pipeline stages importing `rmu.mapping.providers`; extending the same rule to `rmu.ai` keeps the boundary mechanical. Session code keeps one seam (providers), so `--assist` switching changes provider construction only — artifact shapes are provably identical (FR-009: same `Proposal` dataclass feeds `build_draft`/lineage regardless of mode).

## R9 — Proposal persistence & regeneration (FR-016)

**Decision**: No new mechanism — `MappingSession.proposals` (JSON) already persists proposals at `map start`; the review sheet and approve flow read the session row, not the provider. Additions: each persisted proposal gains `provider` and `asset` provenance keys (values like `local:bge-small-en-v1.5`, `local:qwen3:4b`, `external:claude-*`, recorded per proposal); new JSON column `assist_stats` on `mapping_sessions` (nullable, additive Alembic migration) holding `{mode, client, shown, dropped: {reason: n}, generated_at, assets}`; new command `rmu map regenerate --session N` explicitly replaces the persisted set (old set moved into `assist_stats.superseded` for the audit trail).

**Rationale**: The existing design already had "generate once, persist" semantics — the clarification is satisfied by surfacing provenance + drop counts, not by new storage. `mapping_sessions` is not one of the four append-only registries, so an additive column is constitutionally safe; existing rows read as `assist_stats = NULL` (renders as "pre-002 session").

## R10 — Performance budget (SC-008)

**Decision**: Budget allocation on the A9 reference machine: embedding both field-descriptor sets < 5s (dozens of short strings); LLM value-map proposals ≤ ~30s per value-map at temp 0 with a compact prompt; whole-exemplar generation target ≤ 5 min enforced by a per-call timeout (default 120s, config) — a timed-out tier degrades exactly like an absent one (message + counts, session continues). Progress feedback: per-step lines on stderr during `map start` ("ranking fields… proposing value maps (2/3)…").

**Rationale**: Timeouts convert the pathological-slow-path risk into the already-specified degradation behavior instead of a hung session; budgets are asserted loosely in an integration test marked `slow` (skipped when assets absent).

## Dependency delta (pyproject) — as built

- Add: `fastembed>=0.8` (main; installed 0.8.0, pulls onnxruntime + tokenizers, no torch).
- **Not** added: `ollama` — the tier-2 client is stdlib `urllib` (see R2 build-time revision).
- No change to `anthropic` (external tier unchanged).
- Dev: none new (fake Ollama server is stdlib `http.server`).

## Assumption log updates

Recorded in `ASSUMPTIONS.md` alongside this plan (Principle IX):
- **A12a**: embedding stack = fastembed + `BAAI/bge-small-en-v1.5` (MIT); licenses verified against 2026 ecosystem surveys at plan time, re-verified at install.
- **A12b**: local LLM = Ollama `qwen3:4b` (Apache-2.0), temp 0, JSON-constrained; fallback `gemma3:4b`.

Sources consulted (plan-time verification of A12): [BentoML — open-source embedding models 2026](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models), [HuggingFace — local LLMs 2026](https://huggingface.co/blog/daya-shankar/open-source-llm-models-to-run-locally), [local LLM comparisons 2026](https://klymentiev.com/blog/best-local-llm), [PocketLLM 2026 roundup](https://pocketllm.app/blog/best-local-llm-models-2026/).
