# STATUS — Report-Mapping Utility v1

Terse build state for the business side. Newest session first.

## Session 2026-07-16 — feat(005): matrix-aware target onboarding, Phase 1 built

Feature 005 Phase 1 (branch `005-matrix-target-onboarding`, design + plan in
docs/superpowers/): grid targets like the Eskom checklist now onboard as a
**criteria × tower matrix** instead of 373 flat regions named `10_10`.

Built (subagent-driven TDD, every task independently reviewed; suite green
except one PRE-EXISTING unrelated `test_seed.py` idempotency failure — predates
the branch, tracked below; ruff clean):
- `onboard/matrix.py` — deterministic axis reconstruction: row axis (criterion
  number+text columns paired), column axis (tower headers), every blank cell
  referencing `(row_id, col_id)` with derived names (`corrosion__t2`) + a human
  label ("Corrosion × T2"). **Per-table**: non-qualifying grids still emit flat
  cells — nothing silently dropped (found + fixed mid-build when the old
  fixture's second grid vanished; now pinned by test).
- `analyze_target` prefers the matrix path for grid forms; old flat path kept
  as the no-tables fallback; `row_axis`/`col_axis` added to the proposal schema.
- `onboard/interpret_matrix.py` — optional AI structural interpretation:
  annotates axis entries with `suggested_*` by grid INDEX only (never
  coordinates), referent-resolution gate drops+counts unknown indices,
  suggestion-only (never overwrites, human confirms). No-op under `--no-ai`.
- `onboard/axis_providers.py` — tiered resolution mirroring 002: local vision
  via loopback Ollama (**new `vision_model` config slot, default
  `qwen2.5vl:7b`**; `qwen3:4b` stays for text tiers — D12), external
  consent-gated and explicitly not-yet-enabled, `none` → deterministic floor.
  `rmu ai doctor` gains a vision line.
- `approve_template` attaches a `matrix` block to `required_schema`
  ({criteria, towers, cell_field}) when axes exist; flat templates unchanged;
  verify-on-approve round-trips cells exactly as before; apply untouched
  (Constitution II intact, invariant-tested incl. strict interpret no-op).

**Decisions/assumptions logged:** D12 (matrix representation + vision model
slot), A14 (blank Eskom template = form spec, template-only external assist
eligibility). **Next:** validate on the real Eskom holdout (expect ~20 criteria
× ~5 towers from the interpret stage vs 373 renames), then Phase 2 — the
axis-first studio review surface (separate plan).

**Open/pre-existing:** `test_seed.py::test_db_init_and_seed_load_idempotent`
fails on this branch's base (predates 005; separate fix). `ollama pull
qwen2.5vl:7b` before first local-vision use; doctor reports its health.

## Session 2026-07-15 (2) — fix: Studio "nothing works" — two headline bugs + dashboard polish

Dogfooded the studio against the real dev DB after the owner reported "loads of
bugs, nothing works, UI/UX clunky." Found and fixed **two real bugs** (both with
TDD regressions), polished the dashboard, and separated genuine bugs from an
automation artifact. Studio suite **166 green**, ruff clean.

**Bug 1 — session view 500 (dangling profile recipe).** See detail below.

**Bug 2 — the core draw-link gesture was broken for every required field.**
`map start` seeds every required target field as a T3 stub route (`from: '?'`,
mapping/session.py:58). The canvas draw gesture (click source → click target,
FR-013) POSTs to `create_route`, which **refused any field already in `routes`**
— i.e. every required field. So on the real workflow you could not draw a manual
link to any field that needed mapping; only optional (non-seeded) fields worked,
which is why the parity tests (they reject a T2 proposal first, then draw on the
now-empty field) stayed green and missed it. **Fix:** `create_route` now ADOPTS a
T3 stub (fills its `from`, recomputes the derived tier), refusing only a real
T0/T1/T2 route (→ re-route/accept, never clobbered). New regressions
`test_draw_link_fills_a_seeded_t3_stub` + `..._still_refuses_over_a_confirmed_route`.
Verified live: drawing on a T3 field returns 200 and the link becomes T0/confirmed.

**UX — dashboard empty-states.** Empty registry sections (Transforms, Value maps,
Apply runs, etc.) rendered as bare column headers with no rows — looked broken.
Added a `{% else %}` muted empty-state line per section ("No approved transforms
yet — approve a mapping session to create one", etc.). Template-only; dashboard
tests green.

**Bug 3/4/5 — three reachable-500 robustness holes (QA sub-agent found; lead
fixed).** A QA pass driving every studio route surfaced three malformed-but-
plausible requests that hit an unhandled exception → HTTP 500 instead of the
studio's uniform 422 refusal:
- **Template approval with a non-integer version** (`proposals.py` — `int(tver)`
  after only checking `@` is present): the approve form is a free-text
  `name@version` box, so a typo like `ias.defect_form@v1` / `@` / `@1.0` crashed
  the server. Now validated → clean 422 refusal.
- **Value-map staging with unequal parallel columns** (`valuemaps.entries_from_
  parallel` `zip(strict=True)`): a partial/hand-built POST 500'd. Now a 422.
- **Path-traversal value-map name** (`name` form field became a draft filename
  unsanitised): now rejected at the boundary (CLAUDE.md: validate at system
  boundaries).
Fixes in `routes/proposals.py` + `routes/links.py`; QA's pins in
`tests/studio/test_route_robustness.py` converted from xfail to passing
regressions (+ a new path-traversal case). QA also VERIFIED clean: FR-006
terminal read-only (8 mutating routes all 422 on approved sessions; zero
hx-post forms), FR-031 approval-gate parity, base_hash validation on every
draft mutation, and register-&-pin's pre-INSERT lease check.

**UX polish (sub-agent):** studio.css restyled within existing selectors —
per-tier left-edge stripe on link/triage rows (amber pending / red missing /
green confirmed scannable down hundreds of rows), machine keys in a mono face,
readiness bar with a label + tier dot-markers + tabular counts + next-blocking
CTA, crisper rail hover/active, unified chips/buttons, reduced-motion honoured.
Dashboard empty-states added by the lead (bare-header sections now read as
intentional). Presentation only; all JS/test hooks preserved.

**NOT a bug (automation artifact):** the source/target PDF panes appear blank
under headless browser automation because a backgrounded tab throttles
`requestAnimationFrame`/`IntersectionObserver` (PDF.js renders pages lazily on
scroll). Proven fine by rendering a page manually in-tab; a foreground browser
(real usage) paints normally. Recorded as a memory so future studio debugging
doesn't chase it.

**Recommended (NOT done — needs owner decision, touches append-only rows):** the
real dev DB carries a dangling profile `scopito.distribution@1` (registered by
onboarding proposal 2 but its recipe YAML was deleted in the 2026-07-14 hygiene
cleanup) and session 1 hangs off it targeting the 373-region Eskom holdout.
The studio now tolerates this gracefully, but for a clean demo state consider
abandoning session 1 (a normal lifecycle transition) and/or restoring the recipe.
Left for the owner — deleting registered artifacts conflicts with Constitution III.

### Bug 1 detail — session view 500 (dangling profile recipe)

**Symptom** (dogfooding the studio on the real dev DB): the dashboard, proposals
and AI pages load, but opening the ONE mapping session (`/sessions/1`, the
headline canvas) returns **500 Internal Server Error** — so from the owner's
seat the studio's main surface "doesn't work."

**Root cause:** `studio/geometry._source_boxes` re-reads the profile *recipe
YAML* (`profile_config`) purely to draw source-side spatial overlay boxes. The
real DB's active profile `scopito.distribution@1` (registered by onboarding
proposal 2) has **no recipe file on disk** — the untracked experimental
profile YAMLs were deleted (checkout-hygiene, flagged in the 2026-07-14 entry)
but the DB row remained. `profile_config` raised an uncaught `FileNotFoundError`
→ 500. Confirmed a studio-only divergence: `rmu map review/preview --session 1`
**succeed** on the same session (they read the stored extraction, not the
recipe), so the studio broke where the CLI does not — violating FR-002
interchangeability.

**Fix** (TDD; studio suite 164 green, ruff clean): `_source_boxes` tolerates a
missing/unreadable recipe (`FileNotFoundError`/`OSError` → `[]`). Spatial boxes
are a projection aid, never source-of-truth; the canvas renders from the stored
extraction exactly as the CLI does. New regression
`test_source_boxes_tolerate_missing_profile_recipe`. Verified end-to-end: every
studio route on the real DB now returns 200 (`/sessions/1`, `/sessions/1/geometry`,
`/dashboard`, `/proposals/1-3`, `/ai`).

**Investigated & NOT a product bug:** the source/target PDF panes look blank
under headless browser automation because a backgrounded tab throttles
`requestAnimationFrame`/`IntersectionObserver` (PDF.js renders lazily on scroll).
Proven fine by rendering a page manually in-tab; a foreground browser (the
owner's real usage) paints normally. **Open (UX, not yet actioned):** owner
reports the surfaces feel "clunky" — needs a direction (empty dashboard sections
show bare headers; the Eskom target's 373 un-renamed grid regions make a very
long cryptic link list). Awaiting owner priorities before any redesign.

## Session 2026-07-15 — feat(004): Mapping Studio (D6) — full vertical slice

Built the **Mapping Studio** (feature 004, per D6/D9): a strictly-local,
single-user web app that is now the PRIMARY human-in-the-loop surface, with the
CLI still canonical for batch. Implemented as a **deletable `rmu.studio`
subpackage** (FastAPI + uvicorn behind an optional `studio` dependency group;
HTMX + PDF.js vendored — logged as **D11 / A13** in ASSUMPTIONS.md). Launched
with `uv run rmu studio` (127.0.0.1 only, per-launch secret in the URL).

**All 53 tasks done; 227 pre-existing tests + 159 new studio tests green; ruff
clean; suite green WITHOUT the studio group installed (SC-004).**

Delivered, all seven user stories:
- **Dashboard** — registries, sessions, proposals, runs (SafeCard verdicts +
  coverage + exceptions), AI health + per-client consent grant/revoke.
- **Visual mapping canvas** — source & target rendered as real pages, element
  overlays (bbox×scale, correct on rotated pages), focus wires + colour
  pairing, tri-directional selection, draw/accept/reject/re-route links,
  readiness bar fed by the *actual* approval gate.
- **Link detail & value mapping** — observed values, staged value-map editing,
  explicit Register & pin (append-only version), constants/formulas/prompts;
  tier derived from mechanism (T0/T1), never hand-picked.
- **Preview & approve** — native/honest preview (PDF inline, CSV table, docx
  as the real file), same gate + same stored Transform as `rmu map approve`.
- **Visual onboarding review** — PDF-first keyboard triage (Y/E/X + auto-
  advance), drag/resize + draw-new regions, bulk-confirm, verify-on-approve
  per-check report, post-approval next-step offer.
- **Initiation** — start sessions / onboarding drafts from browser uploads
  (content-addressed → identical artifacts), verbatim CLI refusals, drift→
  re-onboard shortcut in the run view.
- **Locality & deletability** — loopback bind + per-launch secret + Host/Origin
  checks (every route), no browser-persisted data, import invariant, deletion
  drill.

**Load-bearing rule honoured (D6):** the studio owns ZERO business logic — every
action delegates to the exact CLI code path. Enforced by ~50 parity/audit tests
(byte-equal drafts, row-equal registry writes, bidirectional cross-surface
finishability) plus `tests/invariants/test_no_studio_in_core.py`. CLI bodies
for `map start/regenerate/preview/approve/abandon`, `valuemap create`, and
`onboard draft-*` were refactored into shared functions (no behaviour change);
added `rmu map abandon`.

**Manual demo checklist** (quickstart.md) — not automatable, for the Gate-2
demo run on real hardware: rotated-overlay eyeball on the Eskom holdout, SC-010
5-second open on a 100+-page exemplar, SC-008 <30-min holdout triage, SC-009
unaided first-attempt canvas journey.

**CLI behaviour deltas from the refactor (intentional, not regressions):**
- `rmu map approve` now refuses a non-draft session (`approve_session` guards
  `status != draft`) — previously it would have registered a second Transform
  from an already-approved session. This also closes the racing-approval hole
  across surfaces (studio + CLI can't double-register).
- `parse_transform` now reports malformed-YAML drafts as a `TransformValidationError`
  (one clean refusal) instead of a raw parser traceback — improves both surfaces.

**Post-review fixes (independent code review, 2026-07-15):** register-&-pin now
draft-conflict-checks BEFORE the registry INSERT, so a conflicting register can
never orphan/duplicate a ValueMap version (FR-003 row-parity on the FR-005
path); a global `TransformValidationError` handler returns 422 (not 500) if a
draft is hand-corrupted. Both regression-tested. Full review recorded in
`specs/004-mapping-studio/checklist-review.md`.

**Open:** `starlette.testclient` emits a deprecation warning (httpx vs httpx2);
cosmetic. PDF.js/HTMX vendored versions pinned in `static/vendor/VENDOR.md`,
updated manually.

## Session 2026-07-14 (2) — fix: overlay render on /Rotate pages + verify read-back

**Symptom:** `onboard approve` of the Eskom holdout target (grid-region
proposal from the previous session) failed verify-on-approve with EVERY
region `<empty region>`. Two stacked root causes, both found on the real PDF
and invisible to the synthetic fixtures:

1. **Renderer ignored page rotation.** The Eskom pack is a portrait mediabox
   displayed landscape via `/Rotate 90`. Region bboxes are registered in
   pdfplumber's rotation-aware visual space (detection + roundtrip verifier
   agree), but `render_overlay_pdf` drew at those coordinates on the raw
   unrotated page — all text landed 90° away from its region. Fix: per-page
   CTM transform (90/180/270) so drawing happens in visual space.
2. **Verifier word-split by template furniture.** The Word-exported grid
   carries literal space characters inside cells; pdfplumber `extract_words`
   interleaves them with the rendered value, splitting `S1` into `S 1` and
   faking a mismatch. Fix: roundtrip read-back now compares the region's
   non-space CHARS in reading order, not word segmentation.

TDD both: new `test_overlay_respects_page_rotation` (parametrized 90/180/270)
and `test_overlay_roundtrip_survives_template_space_chars`; suite 201 green,
unrotated golden coordinates byte-identical. **Result:** `rmu onboard approve 1
--name eskom.annex.c@1 --by rayno` registers TargetTemplate `eskom.annex.c@1`
(id 1) — the real Eskom checklist is now an onboarded target.

**Open:** roundtrip in-region char match is substring-based (`expected` sans
spaces in region chars) — honest for presence, but a value equal to template
furniture text would self-match; fine for verify-on-approve sample values.

## Session 2026-07-14 — feat: grid-region detection for fixed-layout targets

**Symptom** (onboarding the Eskom inspection checklist holdout as a target
template): proposal contained only the default cardinality element — useless.
**Root cause:** `analyze_target` fixed-layout pass only pairs `Label:` text
with area rectangles; the Eskom form draws its grid as ~500 1pt hairline rects
per page (lines, not boxes) and labels fields via grid rows/columns, so zero
regions were found. The structure IS recoverable: pdfplumber line-strategy
table reconstruction yields 458 cells / 373 blank across 4 pages.

**Built** (spec `docs/superpowers/specs/2026-07-14-grid-region-detection-design.md`,
plan `docs/superpowers/plans/2026-07-14-grid-region-detection.md`; suite 197
green, ruff clean):
- `_grid_region_elements` fallback in `analyze_target.py`: when the label+box
  pass finds nothing, reconstruct the line grid and propose every blank,
  size-valid cell as an overlay_region (bbox+page), named best-effort from its
  row label, else column header, else position; analyst renames in review
  (accepted bar: reviewable regions, human names them; all blank cells,
  size-filtered only).
- New fixture `target_grid.pdf` (lines only, degenerate sliver column, blank
  2x2 grid) + unit and e2e tests; existing fixtures byte-identical; label+box
  path untouched (fallback only).
- **Verified on the real Eskom PDF:** 373 regions (was 0) — 269 row_label,
  104 positional, spread 99/104/95/75 over the 4 pages. Name quality is
  best-effort (long checklist prose truncates; numeric label cells slug to
  numbers) — renaming stays a human review step.

**Also fixed while verifying (dogfooding fallout):**
- `seed load` crashed on any recipe written by `onboard approve`
  (`effective_from` quoted string vs date) — loader now accepts both.
- `test_regenerate_refused_on_approved_session` skipped its env bootstrap and
  ran against the REAL dev DB (polluting it; outcome depended on dev state).
- ⚠️ Checkout hygiene: `profiles/scopito.pdf.distribution.v1.yaml` +
  `scopito.pdf.solar.v1.yaml` (untracked, from onboarding experiments against
  a reset DB) — distribution@v1 claims the same fingerprint shape as seeded
  `scopito.pdf.powerline@v2020`, so any freshly seeded DB (incl. test envs)
  becomes ambiguous and `map start` blocks. Recommend deleting them; approve
  into a seeded DB would have collision-blocked them (FR-024).

**Open:** Zeitview thermal-roof (non-tabular narrative) and CID/broken-font
PDFs (Tower demo) remain separate problems, diagnosed 2026-07-13, not built.

## Session 2026-07-13 — fix: onboarding table detection on indented headers

**Symptom** (found onboarding the real Scopito seed demos): `onboard approve`
failed with `row_count_exact` mismatch + `fingerprint_no_collision` on the
distribution demo, and `no confirmed record_table element` on the transmission
demo. **Root cause:** the record-table detector (`onboard/analyze_source.py`
pass 2) built column x-ranges from the **header** word positions, but these
exports indent the header a few points RIGHT of the data rows — so every data
cell fell outside the ranges, the real header was rejected, and the detector
fell back to using the **first data row as the header** (garbage columns, a
literal one-row `table_header_regex`; transmission got no table at all). A
secondary issue: `recurrence` came from a fill-thresholded heuristic count that
the deterministic extractor never reproduces, so `row_count_exact` was a
spurious mismatch. The synthetic fixtures hid it — they draw header and data at
identical x-positions.

**Fix** (branch `003-pdf-format-onboarding`, full suite 191 green, ruff clean):
1. Column boundaries now sit at **midpoints** between header words, with the
   first column extended to the left page edge (catches left-indented data) and
   the last kept to a bounded `+60` margin (a far-right sentinel let header-block
   lines masquerade as tables — regressed `survey_report_a`, caught + fixed).
2. `recurrence` (and the stored row set) is recomputed by the extractor's
   `row_pattern` rule, not the detection fill-threshold, so analysis == apply by
   construction and `row_count_exact` is a real determinism guard.
3. New regression fixture `survey_report_indented.pdf` (indented header + sparse
   rows) + unit/e2e tests; existing committed fixtures byte-identical.

Verified read-only on the real demos: distribution now detects the true header
and all **10** rows (was eating row 1 as the header); transmission detects a
table at last. Both still (correctly) BLOCK at `fingerprint_no_collision` as
duplicates of `scopito.pdf.powerline@v2020` — they are the same shape that
profile already handles, not new profiles.

**Open / follow-ups:**
- The Zeitview thermal-roof holdout is a **non-tabular** narrative report
  (full-page anomaly cards, no Id/Severity register) — needs a separate
  record-card detection strategy; not addressed here.
- Transmission mixes 6-/7-digit IDs, so its 7-digit row (`1050227`) is dropped by
  dominant-class filtering (`^\d{6}$`) — a proposal-quality item the analyst
  broadens in review, distinct from this bug.
- Optional cleanup: factor a shared `iter_record_rows()` used by both the
  analyzer and `recipe_pdf.extract` (row loops are currently mirrored by hand).

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

---

## Session 2026-07-12/13 — feature 003 (pdf-format-onboarding) BUILT

**Done**: full spec-kit cycle (spec w/ 4-round clarify+brainstorm → plan → 36 tasks →
implement) on branch `003-pdf-format-onboarding`, PR #5. Assisted onboarding shipped:
`rmu onboard draft-profile|draft-template|review|approve|abandon`. Heuristic structural
analysis (3-pass, deterministic) proposes extraction recipes / template schemas with
per-element structural confidence; optional 002 local-LLM naming hints (--no-ai clean);
D1-style YAML + HTML review; verify-on-approve gate (exemplar re-extraction match,
fingerprint self-match + collision check, template test-render round-trip) registers
versioned SourceProfiles (generic `rmu.extract.recipe_pdf` engine — recipes are data)
and TargetTemplates (pdf_form fill + pdf_overlay coordinate/image rendering, mandatory
read-back verification, pinned-metadata determinism). Draft artifacts structurally
cannot be applied (new `onboarding_proposals` table + pre-flight guard, SC-006 tested).
E2E: never-seen shape → onboard → map → batch converts 9/9 records; drift blocked with
seeded re-onboarding hint (FR-021). Full suite + SC-007 byte-identical regression
baseline green; ruff clean.

**Decisions**: D10 logged (pypdf runtime + reportlab dev→runtime; D5/D7 pre-existed).
Zeitview holdout moved to `seed/holdout/` (existing tests sweep source_samples/ — the
move IS the quarantine), kept untracked per owner; `tests/invariants/test_quarantine.py`
enforces zero code references. T025 simplification: template review uses the generic
element sheet (bbox shown as data), page-image overlays deferred to 004 Mapping Studio.

**Next**: Rayno runs scripts/acceptance_003.md against the holdout (SC-001 ≥80% +
SC-003 <30min datapoints) → record here. Then /speckit-analyze or PR review; 004
Mapping Studio remains sequenced behind discovery (D9).

**Open questions**: none blocking. SC-009 perf smoke is marked slow (run:
`uv run pytest -m slow tests/integration/test_perf_smoke.py`).
