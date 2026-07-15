# Implementation Plan: Mapping Studio

**Branch**: `004-mapping-studio` | **Date**: 2026-07-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/004-mapping-studio/spec.md`

## Summary

Build the Mapping Studio (D6/D9): a strictly-local, single-user web app that becomes the primary
HIL surface — visual mapping canvas, link-level value mapping, native preview + approve, visual
onboarding review with keyboard triage, initiation, and a dashboard — while owning **zero business
logic**. Technical approach: a deletable `rmu.studio` subpackage (FastAPI + uvicorn behind an
optional dependency group) serving server-rendered HTML with HTMX fragments; PDF pages rendered
client-side by vendored PDF.js with SVG overlay layers scaled from the registered rotation-aware
coordinates; every route delegates to the exact functions the CLI calls (session build, draft
parse/validate, `check_approval`, verify-on-approve, append-only registry writes); draft-file
conflicts handled by content-hash optimistic concurrency (409 + diff, reload-or-overwrite); a
per-launch URL secret + Host/Origin validation hardens the loopback bind. No new tables, no
migration. Launched via a new `rmu studio` subcommand.

## Technical Context

**Language/Version**: Python 3.12 (uv-managed) — fixed by constitution
**Primary Dependencies**: existing — SQLAlchemy/SQLite, Typer, Jinja2, PyYAML + jsonschema, the
mapping/onboard/apply/render/ai modules as the single write paths; **new (optional `studio`
group)** — FastAPI, uvicorn, python-multipart; **vendored static** — HTMX, PDF.js (pinned,
committed with licenses inside the studio package). Justified in Complexity Tracking; logged as
D11 in ASSUMPTIONS.md before code (Principle IX).
**Storage**: unchanged — SQLite registries, `store/drafts` draft files, `store/objects`
content-addressed PDFs. **Zero new tables/columns; no Alembic migration** (data-model.md).
Per-launch secret in process memory only.
**Testing**: pytest — parity tests (studio HTTP action ≡ CLI action, byte/row equality via
FastAPI TestClient), auth middleware tests (loopback/Host/Origin/token), import-scan invariant
(no core module imports `rmu.studio`), suite-green-without-studio (tests skip when group absent),
HTMX-fragment golden tests, conflict-detection tests. No browser automation (research.md R9).
**Target Platform**: local single-operator machine (macOS dev, modern desktop browser), per A5
**Project Type**: local web front-end as a deletable subpackage of the existing `rmu` CLI tool
**Performance Goals**: SC-010 — 100+-page image-heavy exemplar interactive < 5 s, lazy page
rendering; SC-008 — grid-heavy holdout proposal fully reviewed < 30 min via keyboard triage
**Constraints**: loopback-only bind, per-launch secret, Host/Origin validation (FR-040/040a);
no studio-private state (FR-004); read-only approved artifacts (FR-006); no AI outside assist
providers (FR-044); studio deletable with suite green (FR-042); no document data persisted
browser-side (FR-043); existing refusal/exception messages reused verbatim

## Constitution Check

*GATE: evaluated against constitution v1.0.0 (nine principles). Re-checked after Phase 1 — still passing.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. TBD discipline | PASS | The studio renders registered targets; it invents no target content. Interim templates only; nothing Annexure-H/SAP is fabricated. Approval identity prefill (FR-035a) uses proposal context, not invented registry content. |
| II. Deterministic apply | PASS | Studio never touches apply; batch runs stay CLI-only (out of scope). Preview uses the same non-strict resolve path as `rmu map preview` — no AI at preview or apply (FR-044). AI remains inside existing assist providers, reviewed as persisted proposals. |
| III. Append-only registries | PASS | Studio exposes no mutating action on registered artifacts (FR-006); its only registry writes are the existing append flows (Transform on approve, ValueMap on Register & pin, profile/template on onboard approve). No migration at all this feature. |
| IV. Templates/transforms are data | PASS | The studio edits the same schema-validated draft YAML the CLI edits, re-validated by `mapping.loader.parse_transform` before every write. No route bypasses schema validation; no format knowledge in studio code. |
| V. No false confidence | PASS | Tier colour language reused (T0/T1/T2/T3); tiers are derived from mechanism (FR-013a), never hand-picked; readiness bar is `check_approval` itself, never a parallel calculation (FR-019); field-name overlap never shown as confidence (FR-016); docx previews are never HTML lookalikes (FR-030a). |
| VI. Decoupled stages | PASS | `rmu/studio/` sits beside the pipeline like `mapping/` and `onboard/` do; it calls their public functions and touches no stage internals. Reverse imports banned by a new invariant test in the `test_no_ai_in_apply.py` pattern (FR-042). Refactors extract CLI command bodies into shared functions — orchestration moves, behavior doesn't. |
| VII. Data sensitivity & `--no-ai` | PASS | Studio is loopback-only + per-launch secret; no document data leaves the machine. Assist resolution unchanged: local default, manual always fully functional, external strictly consent-gated with the requirement explained, not bypassed (FR-036/FR-044). Dev/test on seed + synthetic fixtures. |
| VIII. Test-first on invariants | PASS | Failing tests precede code for: parity (SC-002/SC-005), auth refusal (SC-003/SC-011), import invariant + suite-green-without-studio (SC-004), no-writes-outside-existing-artifacts audit (SC-006), conflict block (FR-005). Existing determinism/append-only/drift tests remain untouched and must stay green throughout. |
| IX. Assumption traceability | PASS (action required) | D11 (studio dependency group + vendored HTMX/PDF.js) MUST be logged in ASSUMPTIONS.md as the FIRST implementation task; code and commits cite D6/D9/D11. |

## Project Structure

### Documentation (this feature)

```text
specs/004-mapping-studio/
├── spec.md              # Feature specification (clarified + 3 brainstorm rounds)
├── plan.md              # This file
├── research.md          # Phase 0 — stack, rendering, deletability, concurrency, auth decisions
├── data-model.md        # Phase 1 — no new entities; existing-entity access map; ephemerals
├── quickstart.md        # Phase 1 — install, launch, acceptance journey, manual demo checklist
├── contracts/
│   ├── http-routes.md   # Studio HTTP surface (routes → existing code paths, error contract)
│   └── cli-studio.md    # `rmu studio` subcommand contract
└── tasks.md             # (/speckit-tasks output — not created here)
```

### Source Code (repository root)

```text
src/rmu/
├── studio/                      # NEW deletable subpackage (optional `studio` dep group)
│   ├── __init__.py
│   ├── app.py                   # FastAPI app factory; route registration
│   ├── auth.py                  # middleware: loopback peer, Host allowlist, Origin, launch token
│   ├── launch.py                # server start, port pick, secret generation, browser open
│   ├── concurrency.py           # DraftLease hashing, 409 + diff (FR-005)
│   ├── geometry.py              # registered-bbox → client geometry JSON (projection only)
│   ├── routes/                  # thin handlers per area: dashboard, sessions, links, preview,
│   │   └── ...                  #   proposals, initiation, ai — each delegates per contracts/http-routes.md
│   ├── templates/               # Jinja2 pages + HTMX fragments (readiness bar, link list, triage rail)
│   └── static/
│       ├── studio.css           # dark-graphite chrome, tier colour tokens (FR-017)
│       ├── js/                  # small hand-written modules: overlay scaling, focus wire,
│       │                        #   drag/resize regions, keyboard triage — no framework
│       └── vendor/              # pinned htmx.min.js, pdf.mjs, pdf.worker.mjs + licenses
├── mapping/ onboard/ apply/ …   # UNCHANGED except: extract inlined CLI orchestration into
│                                #   plain shared functions where the studio needs the same action
└── cli.py                       # registers `rmu studio` via lazy import (actionable msg if absent)

tests/
├── studio/         (parity vs CLI, auth refusals, conflict 409, fragment goldens, geometry
│                    projection incl. rotated pages; module-wide skip when group absent)
└── invariants/     (NEW: no core module imports rmu.studio — test_no_studio_in_core.py;
                     existing invariants untouched)
```

**Structure Decision**: one new `studio/` subpackage mirrors how `mapping/` and `onboard/` sit
beside the pipeline (Constitution VI): surfaces call stage/session functions, never the reverse.
Handlers stay thin enough that the parity tests are meaningful — any logic a handler grows beyond
"call existing function, render result" is a review-time defect (FR-001). Deleting `src/rmu/studio/`
plus `tests/studio/` leaves the suite green (FR-042/SC-004).

## Execution Strategy

### TDD Requirements

- [ ] `studio/auth.py` [TDD]: SC-003/SC-011 are 100% claims — refusal tests (non-loopback peer,
      forged Host/Origin, missing/stale token, secret-not-on-disk) precede the middleware.
- [ ] Parity harness [TDD]: byte/row-equality tests (studio action ≡ CLI action on the same
      draft: route edits, valuemap register+pin, approve, onboard review/approve, initiation)
      precede the route implementations — they define FR-001/FR-003/SC-002/SC-005.
- [ ] `studio/concurrency.py` [TDD]: FR-005 conflict block (409 + diff, reload/overwrite,
      never silent) tested before wiring into any mutating route.
- [ ] Import invariant + suite-green-without-studio [TDD]: `test_no_studio_in_core.py` and the
      group-absent skip behavior written in the foundational phase, before routes exist.
- [ ] `studio/geometry.py` [TDD]: projection of registered visual-space bboxes (incl. rotated
      holdout pages) to scaled client coordinates — SC-007's testable half.

### Parallel Execution Opportunities

- [ ] Mapping-side surfaces (US1 canvas, US3 link detail, US2 preview/approve) and
      onboarding-side surfaces (US4 review/triage) share only the app shell + auth + concurrency —
      parallelizable once the foundational phase lands. [SUBAGENT]
- [ ] Dashboard/US6 and initiation/US5 are read-heavy and independent of the canvas work. [SUBAGENT]
- [ ] Vendoring + static shell (css, rail, dark chrome) can proceed alongside any story.

### Human Checkpoints

1. After foundational phase — `rmu studio` launches, auth middleware green (refusal tests),
   import invariant + group-absent suite green; D11 logged in ASSUMPTIONS.md.
2. After US1 — open a seed-exemplar session in the browser: overlays land on-region (incl.
   rotated pages), draw/accept/reject links, verify draft YAML via CLI matches.
3. After US2+US3 — full no-YAML session on seed data: value-map register & pin, preview
   (all three target kinds), approve; CLI batch with the resulting transform.
4. After US4 — review the Eskom holdout proposal via keyboard triage; time it (SC-008).
5. Before merge — SC-001 acceptance journey end-to-end + SC-004 deletion drill (remove the
   package, full suite green) + manual demo checklist in quickstart.md.

### Review Gates

- [ ] contracts/http-routes.md route↔code-path table: review before any handler is built —
      it is the FR-001 enforcement surface. [REVIEW]
- [ ] CLI-body refactors (extracting shared functions from `map start` etc.): touch existing
      tested behavior — review before studio consumers land. [REVIEW]
- [ ] `studio/auth.py`: security-sensitive — review before any mutating route is exposed. [REVIEW]

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| New deps FastAPI + uvicorn + python-multipart (stack is "fixed for v1") | Serve the local web surface D6 approved; nothing in the current stack speaks HTTP. Confined to the optional `studio` group so the core install is unchanged. | stdlib `http.server` means hand-rolling routing, multipart uploads, and middleware — more security-sensitive code, not less; Flask offers no typed contract benefit and D6 names FastAPI. Logged as **D11** in ASSUMPTIONS.md. |
| Vendored JS assets HTMX + PDF.js (first committed JS in the repo) | Interactive canvas + in-browser PDF page rendering with zero CDN reliance (locality) and zero build toolchain. | Server-side rasterization adds a native rendering dep to core and re-render round-trips (research.md R2); a JS framework/build step violates the no-business-logic-in-studio posture and personal-hardware simplicity. Same D11 entry. |

*(No principle violations — both entries are deletable stack extensions living entirely inside the studio package.)*
