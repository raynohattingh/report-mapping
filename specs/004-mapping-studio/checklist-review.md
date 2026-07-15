# Code Review — Mapping Studio (feature 004)

**Date**: 2026-07-15 | **Scope**: full feature implementation vs spec / plan / constitution
**Method**: inline critical review (author had full context); constitutional invariants
are mechanically covered by the 161-test studio suite + `tests/invariants/test_no_studio_in_core.py`.

## Spec compliance — PASS

Every user-story acceptance scenario has a passing parity/behaviour test (US1 canvas
route mutations byte-equal to library edits; US2 preview bytes + approval Transform
equal to CLI; US3 value-map stage/register + mechanisms; US4 review-state writes +
verify-on-approve per-check report; US5 upload-start equals CLI start; US6 dashboard
mirrors CLI listings; US7 loopback/deletability). SC-001 acceptance journey passes
end-to-end with zero YAML hand-edits.

## Constitution compliance — PASS

- **II (deterministic apply / no AI at preview)**: preview + approve verified under a
  non-loopback network block (`test_lifecycle_audit`); studio never touches apply.
- **III (append-only)**: only existing append flows write registry rows; no mutation of
  approved artifacts (`test_canvas_parity`, `test_dashboard`).
- **V (no false confidence)**: tiers derived from mechanism (FR-013a), never hand-picked;
  no name-overlap signal rendered.
- **VII (--no-ai / consent)**: local default, external consent-gated + explained.
- **VI (decoupled)**: `test_no_studio_in_core` (import + AST scan) proves no core module
  imports the studio; suite green with the package absent.

## Findings

### Important — FIXED

**F1. Malformed analyst YAML → HTTP 500 instead of 422** (confidence 95).
`routes/links.py` (formula spec) and `routes/proposals.py` (`edit_element` correct,
`add_element`) called `yaml.safe_load` on analyst free-text; `yaml.YAMLError` was
uncaught. Reproduced with `spec: "fn: [unclosed"`. **Fixed**: `_parse_yaml` helper
converts parse errors to a `DomainRefusal` (422) and leaves the draft untouched;
regression tests added (`test_malformed_formula_yaml_returns_422_not_500`,
`test_malformed_corrected_payload_returns_422`).

### Suggestion — not actioned (benign)

- `register_valuemap` commits the ValueMap version before the draft-pin; a 409 on the
  pin would orphan an unused version — harmless in an append-only store (identical to
  `rmu valuemap create` without a pin).
- `preview.html` re-implements PDF.js mounting inline instead of reusing
  `viewer.js:mountPdfPane` — minor DRY.

## Round 2 — independent reviewer (general-purpose subagent, fresh context)

Dispatched a code-reviewer subagent (no session history) against the staged diff. It
confirmed the load-bearing claims hold under scrutiny — security ladder sound
(Origin-absent branch is not a hole given SameSite=Strict + header token), delegation
real (byte/row parity tested not mocked), determinism + append-only preserved,
deletability proven. **Zero critical.** Findings:

### Important — FIXED

**F2. `register_valuemap` committed the ValueMap version *before* the draft-conflict
check** (`routes/links.py`). On the expected FR-005 conflict path, `create_value_map`
committed version N, then the pin raised 409; the analyst's overwrite-retry re-POSTed
and created version N+1 — orphaning N and diverging from the CLI's one-create-per-
register (FR-003 row-parity). **Fixed**: the lease is pre-checked *before* the registry
INSERT, so a conflicting register aborts with 409 and creates no version. Regression
test `test_register_conflict_creates_no_orphan_version`.

### Minor — FIXED

**F3. GET routes 500 on a hand-corrupted draft.** `parse_transform` in GET handlers had
no guard; malformed YAML/schema → uncaught 500. **Fixed**: `parse_transform` now wraps
`yaml.YAMLError` into `TransformValidationError`, and a global studio exception handler
renders it as a 422 refusal — fixes every GET/mutation path and the CLI uniformly.
Regression test `test_corrupt_draft_get_returns_422_not_500`.

### Minor — noted, not actioned

- **F4** `GET /preview/file` rebuilds the artifact (deterministic; behind auth) — mild
  idempotency smell, left as-is.
- **F5** DraftLease read-modify-write isn't atomic under FastAPI's threadpool —
  near-zero impact (single-user, HTMX-serialised UI); documented as accepted.
- The `map approve` terminal-status guard is an intentional CLI behaviour delta (also
  closes the racing-approval hole) — noted in STATUS.md.

## Result

**366 tests pass** (163 studio + 203 pre-existing); ruff clean; suite green without the
studio group. Two review rounds (author inline + independent subagent); every Important
finding fixed and regression-tested. **Assessment: ready to merge.**
