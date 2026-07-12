# STATUS — Report-Mapping Utility v1

Terse build state for the business side. Newest session first.

## Session 2026-07-12 (later) — fix: local LLM proposals were all dropped

**Symptom** (found while dogfooding the quickstart with a real `qwen3:4b`): every
field stayed T3, no AI routes. **Root cause:** Ollama `format:"json"` only
guarantees *valid* JSON, and qwen3 (like most models) returns a top-level
**object**, not the array the gate required — so the whole response was dropped
as one schema failure (`shown=0 dropped=1`). Confirmed by raw curl (`think:false`
did not change it — thinking was NOT the cause).

**Fix** (branch `fix/local-llm-json-array`, 115 tests green):
1. Gate coerces object shapes to a list (`{"proposals":[...]}`, other wrapper
   keys, or a lone proposal object) before validation — defensive backstop.
2. `LocalLLM.complete_json` now uses **Ollama structured outputs** (passes a JSON
   schema as `format`, forcing `{"proposals":[...]}`) and sends `think:false`.
3. Prompt hands the model the EXACT allowed source paths + target field names and
   asks for the object wrapper, cutting referent-resolution drops.

Strict per-item validation is unchanged (bad items still dropped + counted). New
tests cover the coercion (unit) and the object-shaped response end to end (fake
Ollama). Verify on real assets: `rmu map start --assist local` now populates T2
routes; `rmu map review` banner shows `shown>0`.

## Session 2026-07-12 — feature 002 local AI assistance implemented (all 32 tasks)

**Done** (feature `002-local-ai-assist`, branch `002-local-ai-assist`, 46 new tests,
111 total green, ruff clean, golden files byte-identical):

- **Local AI, zero data leaves the machine.** New `src/rmu/ai/` package behind the
  existing `ProposalProvider` seam. Three assistance modes (`none` | `local` default
  | `external`), chosen by `--assist`/config; `--no-ai` is an alias for `none` and
  stays the degradation floor. AI is still session-only — apply/validate/render/audit
  untouched, invariant + golden suites pass unmodified (SC-004).
- **Tier 1 (embeddings, always on-machine):** fastembed + `bge-small-en-v1.5`
  in-process (no sockets at all). Ranks candidate target fields per source field —
  **SC-002 measured 100% top-3** on the committed example-transform routes (bar is
  90%). Also powers `rmu profile suggest`. Realistic per-field `field_labels` added
  to the interim template schemas as data (this is what lifts `issues→defect_code`
  and `severity→priority` into range).
- **Tier 2 (local LLM, optional):** loopback-pinned Ollama (`qwen3:4b`, temp 0, JSON
  mode) via **stdlib urllib** (no `ollama` dep — see A12b/research R2) proposes
  value-map entries with rationales. Every proposal passes a strict two-stage gate
  (JSON Schema + referent resolution); malformed/unresolvable output is dropped and
  only ever shown as an aggregate count (FR-008).
- **Per-tier degradation** (clarified): embeddings-only still ranks; no assets ⇒
  behaves like `none`. Nothing crashes, nothing auto-downloads (`rmu ai setup` is
  the manual path; `rmu ai doctor` reports health).
- **Consent gate:** `external` refuses (exit 4) without a recorded per-client entry;
  `rmu ai consent grant|revoke|list` are the only writers of `<store>/ai.yaml`.
- **Provable offline:** `test_local_session_offline.py` runs a full local session with
  all non-loopback sockets blocked and still produces proposals (SC-001). Loopback to
  a localhost-bound runtime is allowed by design — the claim is "no data leaves the
  machine", verified by a companion localhost-bound check.
- **Persistence/regeneration:** proposals generated once, persisted with provenance +
  `assist_stats` (additive nullable column, migration 0003); `rmu map regenerate`
  replaces them explicitly, prior set kept in `superseded[]`.

**Decisions/deviations logged:** stdlib `urllib` instead of the `ollama` client
(research R2, A12b); `fastembed>=0.8` added, `ollama` NOT added (research dependency
delta). A12a/A12b in ASSUMPTIONS.md updated to as-built.

**Next**: `/speckit-superspec-review` (optional) or review/PR. To exercise tier 2
locally: `ollama pull qwen3:4b` then `rmu ai doctor`. Business-side: 002 is
product-side; willingness-to-pay actions (Dexter escalation, gap test) still lead.

## Session 2026-07-11 (later) — convergence pass closed

**Done**: `/speckit-converge` found 5 partial gaps (0 constitution violations); all 5
implemented (T049–T053, 65 tests green):

1. NEW template versions now register as pure data (`template.json` declares
   name/version/effective_from) — the TBD-1/TBD-2 slot-in mechanism proven by test.
2. Validate stage enforces template validation_rules: vocabulary-illegal values
   (e.g. a defect code outside `defect_codes_v1.csv`) become `invalid_value`
   exceptions and never ship — closes the semantically-wrong-but-structurally-valid gap.
3. One batch run can apply BOTH interim templates (repeatable `--transform`): per
   report the pack AND the defect CSV under a single ApplyRun (`transform_ids`,
   additive migration 0002); regen replays all pinned transforms, hash-verified.
4. `map preview` renders docx sessions as a real (canonicalized) pack file.
5. Duplicate-document handling now regression-tested (converted once, noted).

**Next**: re-run `/speckit-converge` if desired (expected clean), then review/PR.

## Session 2026-07-11 — weekend slice implemented (M1–M4 + M5 drift drill)

**Done** (feature `001-report-mapping-v1`, 48/48 tasks, 56 tests green, ruff clean):

- **M1** — uv/Python 3.12 scaffold; 8 SQLAlchemy models; append-only enforcement
  at the model layer on all five ★ tables incl. ApplyRun (Constitution III);
  Alembic baseline (additive-only, walker-tested); content-addressed store;
  transform-v1 JSON Schema (closed formula grammar, mandatory value-map version
  pins, prompt declarations); idempotent seed CLI (1 profile, 2 INTERIM templates,
  68 defect codes loaded as data).
- **M2** — profile `scopito.pdf.powerline.v2020` as data (anchors/table geometry in
  `profiles/*.yaml`); position-based pdfplumber extractor; BOTH real demo PDFs
  extract clean with `declared == extracted`. ⚠️ A1 finding: the two 2020 PDFs are
  layout *variants* (inline vs stacked header labels; optional `User tags` column) —
  one profile covers both via label-anchored extraction. Detection fingerprinting;
  unknown shape → quarantine. 18 committed synthetic fixtures (seeded reportlab
  builder, incl. one zero-findings report) + 2 drifted fixtures.
- **M3** — HIL mapping session per D1: `rmu map start/review/preview/approve`,
  manual `--no-ai` path built FIRST (D3); AI proposals via provider interface
  (AnthropicProvider, mapping-session-only; StubProvider for tests — zero network
  in the suite); Jinja2 review sheet with T2 rows visually distinct; approval
  refuses T2/T3/unrouted/unresolved pins (exit 3); full lineage persisted (FR-021).
  Live manual session on the Distribution exemplar: approved Transform v1,
  11 decisions recorded.
- **M4** — deterministic batch apply (`rmu apply run`): prompt answers upfront and
  recorded; per-document SafeCard verdicts + batch summary; per-document quarantine
  (unknown/drift/duplicate); per-report defect CSVs + docx report packs
  (OPC-canonicalized: zero embedded timestamps); exceptions.csv ALWAYS; ApplyRun
  written on completion only; `rmu apply regen` reproduces any run hash-verified
  against its manifest using the EXACT recorded transform row.
- **M5 drill** — 22-doc batch (20 healthy + 2 drifted): 20 convert, 2 quarantined
  with no output, both listed in safecard.json + exceptions.csv.

**DoD evidence (SC-001…SC-008)**:

| SC | Evidence |
|---|---|
| SC-001 | Session flow demonstrated live end-to-end (start→edit→valuemaps→review→preview→approve). ≤2h human benchmark deferred per A7 (analysis U1). |
| SC-002 | `tests/integration/test_batch.py`: 20 same-shape reports, zero field decisions, per-report CSVs. |
| SC-003 | `tests/integration/test_drift_drill.py` + `tests/invariants/test_drift_block.py`: both drifted fixtures quarantined, zero mis-conversions, healthy 20 convert. |
| SC-004 | `tests/invariants/test_determinism.py` + golden docx determinism: straight-hash byte identity, re-run twice. |
| SC-005 | `tests/invariants/test_regeneration.py`: manifest hash-verification; a newer transform v2 does NOT leak into regen of a v1 run. |
| SC-006 | `tests/invariants/test_exceptions_report.py` + batch tests: exceptions.csv exists on every run incl. clean. |
| SC-007 | `tests/integration/test_manual_session.py` + `test_ai_session.py`: manual and AI sessions produce identical-form transforms. |
| SC-008 | Both templates flagged `interim=true`, institution `INTERIM`, asserted in `test_seed.py`; zero fabricated Eskom content. |

**Decisions this session** (from the spec-kit clarify/brainstorm, user-approved):

1. Per-document quarantine (blocked docs don't block healthy ones).
2. One defect CSV per source report (consolidated batch CSV = later template addition).
3. Value-map pins live IN the transform (exact versions; growth = new transform version).
4. Per-batch prompt answers: upfront inputs, recorded on the ApplyRun, replayed on regen.
5. Formulas = closed declarative set (concat/substring/regex_extract/date_format/number_format/arith).
6. Document block on anchors-missing OR declared≠extracted; single garbled rows stay record exceptions.
7. Outputs embed NO timestamps (OPC canonicalizer); determinism test is a straight file hash.

**Proposed design-doc deltas** (plan.md "Deviations" — design §7/§8/§1 refinements,
all strictly stronger; please ratify or push back):

- §7: SafeCard verdicts are per-document with a batch summary (was batch-level wording).
- §8: Transforms reference ValueMaps at exact versions (pinning rule made explicit).
- §1: "byte-identical (timestamps excepted)" hardened to "byte-identical, no embedded
  timestamps at all".

**Next**:

- Rayno: run the manual session yourself against the DoD script (SC-001 timing datapoint).
- IAS demo script polish + fresh Scopito samples / TBD-1/TBD-2 via Dexter escalation
  (nudge ~14 Jul); A1 re-verification against current exports when samples arrive.
- Deferred per A7: Zeitview profile, extraction hardening beyond demo+synthetic.

**Open questions**:

- None blocking. AnthropicProvider is implemented but not yet exercised against the
  live API (needs `ANTHROPIC_API_KEY`; demo data only per A6) — worth one manual
  smoke test before the IAS demo.
