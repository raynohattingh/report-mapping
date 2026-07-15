# Contract: Studio HTTP Surface

**Feature**: 004-mapping-studio | **Status**: Phase 1 design contract

Server-rendered HTML + HTMX fragments; JSON only where the client needs raw data (page geometry,
PDF bytes). Every route sits behind the auth middleware (loopback peer → Host allowlist →
Origin/Sec-Fetch-Site on mutations → per-launch token; failure → 403 with restart hint).
All mutating routes are POST, carry `base_hash` when they edit a draft file (409 + diff on
conflict), and execute an existing code path (mapped in research.md R4) — no route contains
business logic.

## Auth & shell

| Route | Method | Purpose |
|---|---|---|
| `/?key=<token>` | GET | Exchange launch token for session cookie; redirect to `/dashboard` |
| `/static/*` | GET | Vendored assets (htmx, PDF.js, studio css/js) |

## Dashboard & registries (US6/P6)

| Route | Method | Purpose |
|---|---|---|
| `/dashboard` | GET | Registries (profiles/templates/transforms/valuemaps: version, status, effective date), sessions + proposals by status, recent runs |
| `/runs/{id}` | GET | SafeCard batch + per-document verdicts, coverage, exceptions report content; drift-blocked docs carry the re-onboard shortcut (FR-037a) |
| `/sessions/{id}/abandon`, `/proposals/{id}/abandon` | POST | Same terminal transition as CLI |
| `/ai` | GET | Doctor report (embeddings, local LLM, degraded) + per-client consent status |
| `/ai/consent` | POST | Grant/revoke — records same fields as CLI (who, when, note) |

## Mapping canvas (US1/P1)

| Route | Method | Purpose |
|---|---|---|
| `/sessions/{id}` | GET | Canvas shell: panes, link list, readiness bar |
| `/sessions/{id}/geometry` | GET (JSON) | Per-page element bboxes (registered visual space), target field/region coordinates, route projections (tier, tag number, state) — the client scales, never computes |
| `/documents/{sha}/pdf` | GET | Raw PDF bytes from content-addressed store for PDF.js (no-store cache headers, FR-043) |
| `/sessions/{id}/routes` | POST | Create manual route (source element → target field); tier derived per FR-013a; decision `manual` |
| `/sessions/{id}/routes/{field}` | POST | Accept (T2→derived tier) / reject (remove) / re-route / delete; decisions `accepted`/`rejected`/`edited` |
| `/sessions/{id}/fragments/links` | GET | HTMX fragment: link list (filterable by tier/state) |
| `/sessions/{id}/fragments/readiness` | GET | HTMX fragment: readiness bar from `check_approval` dry-run + next blocking item |

## Link detail & value mapping (US3/P3)

| Route | Method | Purpose |
|---|---|---|
| `/sessions/{id}/links/{field}` | GET | Detail: observed exemplar values, unmapped values conspicuous, mechanism editor |
| `/sessions/{id}/links/{field}/valuemap` | POST | Stage entries (provenance human/ai-accepted) in the session draft value-map file — no registry write |
| `/sessions/{id}/links/{field}/valuemap/register` | POST | "Register & pin": append-only ValueMap version + pin name@version on route; name suggested from link, analyst-editable |
| `/sessions/{id}/links/{field}/mechanism` | POST | Constant / closed-grammar formula / per-batch prompt (key, label, required) — exactly the schema constructs |

## Preview & approve (US2/P2)

| Route | Method | Purpose |
|---|---|---|
| `/sessions/{id}/preview` | POST | Run non-strict resolve + real render; returns preview panel (PDF pane / CSV table / docx download per FR-030a) with unresolved count and render problems verbatim |
| `/sessions/{id}/approve` | POST | `check_approval` gate; refusals verbatim; success stores the same Transform row (approver identity required) |

## Onboarding review (US4/P4)

| Route | Method | Purpose |
|---|---|---|
| `/proposals/{id}` | GET | Review workspace: pages + spatial overlays, non-spatial list (evidence/confidence/flags), triage rail; structureless proposals show diagnosis with abandon primary |
| `/proposals/{id}/geometry` | GET (JSON) | Element bboxes per page/exemplar; cross-exemplar agreement (FR-032a) |
| `/proposals/{id}/elements/{eid}` | POST | confirm / correct (payload incl. dragged bbox) / remove — writes review_state + corrected_payload |
| `/proposals/{id}/elements` | POST | New analyst-drawn element (evidence source `analyst`) |
| `/proposals/{id}/bulk-confirm` | POST | Per-page bulk confirm of unedited elements — recorded per element |
| `/proposals/{id}/approve` | POST | Verify-on-approve; failure → verify report per-check, grouped, deep-linked to implicated elements; identity pre-filled per FR-035a |

## Initiation (US5/P5)

| Route | Method | Purpose |
|---|---|---|
| `/start/session` | POST (multipart) | profile@version + template@version + exemplar upload (content-addressed) → same artifacts as `rmu map start`; assist mode by existing precedence; drift block surfaces CLI message, no session created |
| `/start/onboarding` | POST (multipart) | draft-profile / draft-template, incl. seeded re-onboarding; CLI rejections verbatim; kind-misuse warning offers explicit proceed-anyway |
| `/sessions/{id}/regenerate` | POST | Re-run assist proposals — same semantics/refusals as CLI |

## Error contract

- 403: auth failure (never leaks which check failed beyond the restart hint)
- 409: draft conflict — body carries the diff + reload/overwrite choices (FR-005)
- 423-equivalent "busy" fragment: database locked by CLI batch/migration — retryable, nothing partially applied
- Domain refusals (gate, drift, unsupported PDF): 422 with the existing CLI message text verbatim
