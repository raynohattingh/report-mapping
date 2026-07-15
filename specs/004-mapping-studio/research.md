# Phase 0 Research: Mapping Studio

**Feature**: 004-mapping-studio | **Date**: 2026-07-14
**Scope**: resolve every technical unknown before design. No NEEDS CLARIFICATION remain in plan.md.

## R1. Web stack: FastAPI + HTMX + vendored assets

**Decision**: FastAPI + uvicorn server, HTMX-driven server-rendered HTML (Jinja2, already a
dependency), all JS/CSS assets vendored into the studio package's `static/` directory. No CDN,
no build step, no SPA framework, no Node toolchain.

**Rationale**: D6 names FastAPI+HTMX+PDF.js as the intent (ASSUMPTIONS.md, design §13.2). Server-
rendered HTML keeps all logic in Python where the existing code paths live (FR-001: zero business
logic in the studio means zero business logic in JavaScript too — the browser renders state, the
server computes it). HTMX gives partial-page updates (readiness bar, link list, element triage)
without a client-side state store, which is exactly FR-004's "no shadow copies" applied to the
browser. Jinja2 is already in the dependency set (review sheets use it). Vendoring satisfies
locality: a studio session must work with no network access at all (Constitution VII spirit;
FR-040 loopback-only would be undermined by CDN fetches).

**Alternatives considered**:
- React/Vue SPA: rejected — duplicates state client-side (FR-004 risk), needs a build toolchain
  on personal hardware, and pushes tier/gate logic into JS (parallel calculation, banned by FR-019).
- Flask: viable, but FastAPI is the D6-named intent, gives typed request/response models for the
  route contract, and uvicorn's loopback bind is explicit.
- NiceGUI/Streamlit-style frameworks: rejected — they own the interaction model; the canvas
  (overlays, wires, drag-resize) needs direct control of the DOM/SVG.

## R2. PDF page rendering: PDF.js in the browser, vendored

**Decision**: Render PDF pages client-side with a vendored PDF.js (page canvas only; no PDF.js
viewer chrome). The server serves the raw PDF bytes from `store/objects` (content-addressed) via
an authenticated route; the browser renders pages lazily on demand (FR-010, SC-010). Element
overlays/highlights are absolutely-positioned HTML/SVG layers on top of each page canvas.

**Rationale**: D6 names PDF.js. Client-side rendering gives lazy per-page rendering, crisp zoom,
and zero new Python native dependencies. Coordinate reconciliation is clean: element bboxes are
registered in pdfplumber's VISUAL rotation-aware space (top-left origin, post-rotation width/height
— established in 003 and re-confirmed by the 2026-07-14 rotation fix in `render/pdf_overlay.py`);
PDF.js viewports are the same visual space scaled by a zoom factor, so overlay position =
`bbox * (rendered_px / visual_pt)` with no rotation math in the studio. The studio never
re-derives coordinates — it scales registered ones (SC-007).

**Alternatives considered**:
- Server-side page rasterization (pdfplumber `.to_image()` / pypdfium2): rejected — adds a native
  rendering dependency to the core install, makes zoom re-render round-trips over HTTP, and puts
  page images in HTTP responses that would then be cached browser-side (FR-043 friction).
- Serving whole PDFs into an `<iframe>` with the browser's built-in viewer: rejected — no overlay
  layer access, no per-page coordinates.

**Vendoring note**: PDF.js (`pdf.mjs` + `pdf.worker.mjs`) and htmx.min.js are committed under the
studio package's `static/vendor/` with their licenses (Apache-2.0 / BSD-2). Pinned versions,
updated manually. They ship inside the studio package so deleting the package removes them (FR-042).

## R3. Deletability: `rmu.studio` subpackage + optional dependency group

**Decision**: The studio lives in `src/rmu/studio/` as one subpackage. Its Python dependencies
(fastapi, uvicorn, python-multipart for uploads) go in a `studio` optional-dependency group
(`uv sync --group studio` / extra). `rmu studio` is registered in `cli.py` via a lazy import that
prints an actionable "studio not installed" message if the import fails. Studio tests live in
`tests/studio/` and skip module-wide (`pytest.importorskip("fastapi")`) when the group is absent.

**Rationale**: FR-042/SC-004 require the full suite green with the studio package absent — an
optional group makes "absent" a first-class installation state, not a simulated one. The import
invariant (no pipeline/mapping/onboard/apply/render module imports `rmu.studio`) is enforced by a
new test in `tests/invariants/` following the existing `test_no_ai_in_apply.py` AST/import-scan
pattern. The lazy CLI import is the single allowed reference, and it is in `cli.py` (a surface,
not a stage).

**Alternatives considered**:
- Separate distribution package (`rmu-studio` wheel): over-engineered for a single-operator local
  tool; complicates the uv workflow for no isolation gain beyond what the subpackage + group give.
- Studio deps in main dependencies: rejected — "suite green without studio" becomes untestable
  as an install state, and core installs drag in a web server.

## R4. Shared code paths: service seams already exist, thin façade only

**Decision**: Studio routes call the same functions the CLI calls, resolved per action:

| Studio action | Existing code path (unchanged) |
|---|---|
| Open/edit session draft | draft YAML at `store/drafts/session_{id}.transform.yaml`; parse/validate via `mapping.loader.parse_transform` |
| Draw/accept/reject/re-route link | edit draft doc + `mapping.session.compute_decisions` for the decisions log |
| Tier derivation (FR-013a) | same mechanism→tier rule design §7 already applied at draft build; exposed read-only, recomputed on mechanism change |
| Readiness bar (FR-019) | `mapping.approve.check_approval` in dry-run form — the gate itself, surfaced as state |
| Preview | same non-strict resolve path as `rmu map preview` (`apply.engine.resolve_record`, strict=False) → real renderers |
| Approve session | `mapping.approve.check_approval` + the same Transform-row store the CLI performs |
| Value maps | stage in the session's draft value-map file; "Register & pin" = same append-only registry write as `rmu valuemap create` + pin edit |
| Onboarding review | `onboard.proposal.Proposal.load(sync=True)` + review-state/corrected-payload writes |
| Onboard approve | `onboard.approve` verify-on-approve; persisted `verify_report` on failure |
| Initiation | same functions behind `rmu map start` / `rmu onboard draft-*` (incl. seeded path) |
| Dashboard | registry queries + runs/SafeCard rows the CLI listings read |
| AI health / consent | `ai.doctor.health` + existing consent records |

Where the CLI currently inlines orchestration in a Typer command body (e.g. parts of `map start`),
that body is refactored to a plain function the command and the studio both call — refactor-in-place,
no behavior change, covered by existing CLI tests. No parallel implementations anywhere (FR-001).

**Rationale**: this is the load-bearing D6 rule. The plan treats any studio-only reimplementation
as a defect. The refactors are the only pipeline-adjacent code this feature touches.

## R5. Draft-conflict detection (FR-005): content-hash optimistic concurrency

**Decision**: When the studio loads a draft (transform YAML, value-map file, or proposal YAML) it
records the file's SHA-256. Every mutating request carries that hash (`base_hash`). Before
persisting, the server re-hashes the file; mismatch → HTTP 409 with a unified diff of
base vs current, and the analyst chooses "reload latest" or "overwrite with mine". Applies
identically to onboarding drafts (which already re-sync YAML→DB on load).

**Rationale**: drafts are files by design (D1 heritage) and the CLI/editor writes them directly, so
locks are unenforceable; optimistic concurrency on content hash detects *any* other writer without
coordinating with it. Hashing whole files is cheap at draft sizes (≤ a few hundred KB). Never a
silent merge (clarification 2026-07-14).

**Alternatives considered**: mtime comparison (unreliable across editors/filesystems); file locks
(CLI won't honor them; stale-lock UX); DB-side version counters (drafts live in files; a counter
misses editor writes — the whole point).

## R6. Launch secret + request authentication (FR-040a)

**Decision**: `rmu studio` generates a per-launch token via `secrets.token_urlsafe(32)`, prints/
opens `http://127.0.0.1:<port>/?key=<token>`. First page load exchanges the URL key for a
`__Host-`-style session cookie (SameSite=Strict, HttpOnly) so the secret doesn't sit in the
address bar/history; every subsequent request must carry the cookie, and every mutating request
additionally an `X-Studio-Token` header (HTMX config), giving CSRF resistance even if SameSite
fails. Middleware validates, in order: (1) peer address is loopback, (2) Host header ∈
{127.0.0.1:port, localhost:port}, (3) Origin/Sec-Fetch-Site on mutations, (4) token. Any failure
→ 403 with a "restart via `rmu studio`" hint. The token lives only in process memory — never on
disk (edge case: stale URL from a previous launch is refused).

**Rationale**: loopback bind alone doesn't stop CSRF/DNS-rebinding from a hostile page in the same
browser, or another local user — the brainstorm round-2 decision. Uvicorn binds `127.0.0.1`
explicitly (same loopback rule `ai.config._is_loopback_host` enforces for the LLM host; the
invariant test asserts the bind address is non-configurable to non-loopback values).

## R7. Preview display per target kind (FR-030/FR-030a)

**Decision**: Preview always runs the real render path into a temp/preview area, then displays:
- **pdf_form / pdf_overlay** → the rendered PDF bytes streamed to a PDF.js pane (same viewer as
  the canvas), unresolved markers visible in the actual output;
- **CSV** → parsed server-side and rendered as an HTML table with `<<unresolved>>` cells flagged
  and counted;
- **docx** → no HTML approximation: the studio shows the unresolved count + per-field resolved
  values, and offers the actual `.docx` file as a download/open-locally link.

**Rationale**: clarification 5 (native and honest — never a lookalike the analyst might approve in
place of the real artifact, Constitution V spirit). Reuses renderers as-is; render problems
(oversize value, missing image, round-trip mismatch) surface verbatim.

## R8. Canvas interaction model (FR-017/018/019, FR-033a, FR-034)

**Decision**: Each rendered page gets an SVG overlay layer for element highlights, numbered tier
tags, and region drag/resize handles; the focus wire is a single SVG path drawn in a full-canvas
overlay only for the hovered/selected link (FR-018). Link list + readiness bar are HTMX fragments
re-rendered from server state after every mutation — the readiness bar fragment is computed by the
same `check_approval` dry-run (FR-019, never a parallel calculation). Onboarding triage is a
keyboard-driven loop (Y/E/X + auto-advance) over a server-held element cursor with state/kind/flag
filters and per-page bulk-confirm, each bulk action recorded per element (FR-034). Region editing
(FR-033a) posts corrected bbox payloads in the registered visual coordinate space (divide by zoom
scale client-side); new analyst-drawn regions post as elements with evidence source `analyst`.

**Rationale**: SVG-on-page keeps coordinates in one space; a handful of small hand-written JS
modules (overlay scaling, wire drawing, drag/resize, keyboard triage) is the entire client-side
footprint — no framework, testable by golden DOM fragments + Playwright-free HTTP tests (see R9).

## R9. Testing approach

**Decision**:
- **Parity/invariant tests (the product claims)**: drive studio HTTP routes with FastAPI's
  `TestClient` and assert byte/row equality against the CLI doing the same action on a copy of the
  same draft (SC-002/SC-005/SC-006); import-scan invariant for FR-042; auth middleware tests for
  SC-003/SC-011 (non-loopback peer simulated via ASGI scope `client`, forged Host/Origin, missing/
  stale token).
- **Fragment tests**: HTMX fragments (readiness bar, link list, triage rail) golden-tested as
  rendered HTML for seed fixtures.
- **No browser automation in CI**: PDF.js rendering and drag interactions are verified by the
  coordinate contract (server serves registered bboxes; client math is `bbox × scale`) plus a
  small manual demo checklist in quickstart.md. SC-008/SC-009/SC-010 are measured manually at the
  M-checkpoint demo, consistent with how 003 measured its SC times.

**Rationale**: everything the constitution cares about (parity, determinism, append-only, honesty,
locality) is server-side and fully testable without a browser; browser-automation infra on personal
hardware is cost without invariant coverage. Studio tests skip cleanly when the `studio` group is
absent (R3).

## R10. New decisions to log in ASSUMPTIONS.md before code

- **D11 (proposed)**: FastAPI + uvicorn + python-multipart added as `studio` optional-dependency
  group; HTMX + PDF.js vendored as static assets inside `rmu.studio`. (Stack is "fixed for v1", so
  the extension is logged, same pattern as D10 for pypdf/reportlab.)
- **A-next (proposed)**: modern desktop browser available on the analyst machine (spec assumption,
  restated as a numbered assumption when implementation starts).
