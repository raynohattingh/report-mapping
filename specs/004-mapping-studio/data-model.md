# Phase 1 Data Model: Mapping Studio

**Feature**: 004-mapping-studio | **Date**: 2026-07-14

## Headline: no new persistent entities, no migration

The studio is a projection layer (FR-004: no studio-private mapping state). **This feature adds
zero database tables, zero columns, and zero Alembic migrations.** Every entity below is either
existing-and-unchanged or ephemeral (process memory / request scope).

## Existing entities (read/written through existing code paths only)

| Entity | Studio reads | Studio writes (via existing path) |
|---|---|---|
| **MappingSession** (row + `store/drafts/session_{id}.transform.yaml` + starter value-map file) | status, draft doc, decisions, assist history | draft edits, decisions entries, status transitions (approve/abandon) — same transitions as CLI |
| **OnboardingProposal** (row + `store/drafts/onboard_{id}.yaml`, `Proposal.load(sync=True)`) | document.elements[], evidence, confidence, flags, verify_report, diagnosis | review_state, corrected_payload, analyst-sourced elements (evidence source `analyst`), approve/abandon |
| **SourceProfile / TargetTemplate / Transform / ValueMap** (append-only registries ★) | listings, versions, effective dates, template PDFs/schemas | append-only only: Transform row on approve; ValueMap version on "Register & pin"; profile/template rows via onboard approve |
| **ApplyRun + SafeCard + exceptions report** | verdicts, coverage, exceptions content, drift-blocked documents (FR-037a) | **never** — strictly read-only (out of scope: batch from studio) |
| **AI health / consent** | `ai.doctor.health` report, per-client consent status | consent grant/revoke — same fields the CLI records (who, when, note) |
| **store/objects** (content-addressed) | exemplar/template PDF bytes for PDF.js | uploaded exemplar files on initiation (same content-addressed store a CLI path-based start produces — FR-036) |

## Ephemeral (never persisted)

### StudioLaunch (process memory only)
- `token`: per-launch secret (`secrets.token_urlsafe(32)`) — never written to disk (FR-040a)
- `port`, `opened_at`
- Dies with the process; a stale URL from a previous launch is refused with a restart hint.

### DraftLease (request/page scope — the FR-005 concurrency token)
- `draft_path`, `base_hash` (SHA-256 of draft file content at load)
- Carried by the client in each mutating request; server re-hashes before persisting.
- Mismatch → 409 + diff; analyst chooses reload-latest or overwrite-with-mine. Not stored server-side.

### Mapping link (visual projection — spec Key Entities)
- NOT stored anywhere. Derived per render from the draft transform's routes; lifecycle
  (create/accept/reject/re-route/delete) is entirely draft-doc edits + decision entries.
- Display attributes derived server-side: tier (per FR-013a mechanism rule), tag number
  (stable ordering by target field), state (confirmed/pending/unmapped).

### ReadinessState (derived per render, FR-019)
- Output of `check_approval` dry-run: fields ready / T2 pending / T3 unmapped / value maps
  unregistered + next blocking item. Never cached, never a parallel calculation.

## Validation rules (enforced by the paths the studio calls — not re-implemented)

- Draft transform edits re-validated by `mapping.loader.parse_transform` before write.
- Approval gates: `mapping.approve.check_approval` (sessions), verify-on-approve (proposals).
- Registry writes append-only (Constitution III) — studio exposes no mutating action on
  approved/registered artifacts (FR-006).
- Region payload coordinates are in the registered rotation-aware visual space; client converts
  pixels→points by dividing by zoom scale, server validates bbox within page bounds.

## State transitions (all pre-existing; studio adds none)

- MappingSession: `draft → approved` (gate) | `draft → abandoned`
- OnboardingProposal: `draft → registered` (verify-on-approve) | `draft → abandoned`;
  element review_state: `proposed → confirmed | corrected | removed` (bulk confirm records
  per-element, indistinguishable from individual confirmation — FR-034)
- Racing approvals across surfaces: second attempt refused by the same gate (edge case) —
  guaranteed by calling the gate, not by studio-side locking.
