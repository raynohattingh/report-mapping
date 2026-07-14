# Feature Specification: Mapping Studio

**Feature Branch**: `004-mapping-studio`

**Created**: 2026-07-14

**Status**: Draft

**Input**: User description: "Add the Mapping Studio (feature 004 per D9): a strictly-local, single-user web application that becomes the PRIMARY human-in-the-loop surface for the mapping utility, per decision D6 (which reversed D1). Instead of editing store/drafts/session_{id}.transform.yaml and onboard_{id}.yaml by hand next to a static HTML review sheet, the analyst SEES the actual documents and connects them visually. Hard constraint carried from D6: the studio owns ZERO business logic — every studio action goes through the exact same code paths as the CLI and produces identical stored artifacts; the two surfaces must remain interchangeable mid-draft. Seven user stories: dashboard, visual mapping canvas, link detail & value mapping, preview & approve, visual onboarding review, initiation from the studio, locality & deletability. Full acceptance journey: one complete session performed entirely in the studio without hand-editing any YAML, then a CLI batch using the resulting transform. Out of scope: multi-user, auth, remote deployment, real-time collaboration, batch runs from the studio, editing approved artifacts, studio-only business logic. Stack choice (D6 names FastAPI+HTMX+PDF.js as the intent) belongs to plan.md, not this spec."

## Clarifications

### Session 2026-07-14

- Q: When does a link-level value-map edit become a registered append-only ValueMap version? → A: Edits stage in the session's existing draft value-map file; a distinct "Register & pin" action creates the new version and pins it on the route (mirrors the CLI starter-file + `valuemap create` flow; no registry version per iteration).
- Q: What happens when the studio detects the draft changed underneath an in-flight edit (FR-005)? → A: Block the save and show what changed; the analyst explicitly chooses "reload latest (discard my edit)" or "overwrite with mine" — never a silent merge or silent loss.
- Q: How does a route get its human-confirmed tier (T0 vs T1) on manual draw / AI accept? → A: Derived from the route's mechanism per design §7 (T0 when fully deterministic — closed value map / constant / formula covering all observed values; T1 otherwise) and displayed; the analyst never hand-picks a tier.
- Q: How is the studio launched? → A: A new `rmu studio` CLI subcommand starts the local server and prints/opens the localhost URL; the loopback-only guarantee is anchored there.
- Q: How are apply-to-exemplar previews displayed for non-PDF targets? → A: Native and honest — PDF previews render inline as pages; CSV previews render inline as a table; docx previews are offered as the actual file to open locally with only the unresolved-marker count and per-field values shown in-studio. Never an HTML approximation of the docx (Constitution V spirit: no lookalike the analyst might approve in place of the real artifact).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Visual mapping canvas (Priority: P1)

As the analyst in a mapping session, I see the source exemplar rendered as its actual pages on the left and the target format on the right, both with multi-page navigation. On the source side, every element of the exemplar's extraction inventory (header fields, record-table columns with a sample of observed values, image regions) is highlighted where it appears on the page. On the target side, a PDF target (`pdf_form` / `pdf_overlay`) renders as its actual pages with its registered fields/regions highlighted, and a CSV or docx target shows its required target fields as a structured panel. Clicking a source element and then a target field creates a route in the draft transform, drawn as a visible link between the panes. AI-proposed routes (tier T2, from the existing assist providers) appear visually distinct as PENDING until I accept (promote to T0/T1) or reject (route removed). Required target fields still at T3/unrouted are conspicuous at all times.

**Why this priority**: This is the headline value of the studio — replacing hand-edited YAML with seeing and connecting the actual documents. It is independently useful on a session created from the CLI: the analyst reviews and edits routes visually even if approval still happens via `rmu map approve`.

**Independent Test**: Start a mapping session via `rmu map start` on a seed exemplar, open the studio session view, verify all extraction-inventory elements are highlighted on the rendered source pages, draw one manual link, accept one AI proposal, reject another, and confirm (by re-reading the draft YAML via CLI) that the routes/tiers changed exactly as if edited by hand.

**Acceptance Scenarios**:

1. **Given** a draft mapping session with AI proposals, **When** the analyst opens it in the studio, **Then** the source exemplar's pages render with each extraction-inventory element highlighted at its page location, the target format shows its fields (rendered pages for PDF targets; structured field panel for CSV/docx targets), T2 routes appear as visually distinct pending links, and every required target field with no route is conspicuously marked.
2. **Given** the canvas is open, **When** the analyst clicks a source element and then a target field, **Then** a route is written into the same draft transform the CLI edits, at a human-confirmed tier, and a link is drawn between the panes.
3. **Given** a pending T2 link, **When** the analyst accepts it, **Then** the route is promoted to T0/T1 (the only way it becomes approvable) and the session decisions log records the same `accepted` action the CLI flow records; **When** the analyst rejects it, **Then** the route is removed and the decision recorded as `rejected`.
4. **Given** a multi-page exemplar and a multi-page PDF target, **When** the analyst navigates pages on either side, **Then** highlights and drawn links stay attached to the correct page and coordinates (including pages displayed via rotation).
5. **Given** any structural-fit indicator shown to the analyst, **Then** it is value-level evidence only — field-name overlap is never presented as confidence (Constitution V), and tier colour language matches the existing review-sheet semantics (T0/T1 confirmed, T2 pending, T3 missing).

---

### User Story 2 - Preview and approve in the studio (Priority: P2)

As the analyst, I trigger an apply-to-exemplar preview and see the rendered result in the target's actual format, with any unresolved-cell markers and their count. When the draft is ready, I approve from the studio; approval runs the same gate as `rmu map approve` and stores the same versioned Transform the CLI would.

**Why this priority**: Closes the session loop — with US1 + US2 an entire mapping session completes in the studio without touching YAML. Depends on US1's session view.

**Independent Test**: On a studio-edited session, trigger preview and compare its output byte-for-byte with `rmu map preview` on the same draft; then approve in the studio and verify the stored Transform row equals what `rmu map approve` produces for the same draft.

**Acceptance Scenarios**:

1. **Given** a draft with unresolved fields, **When** the analyst previews, **Then** the preview is produced by the same resolve path as `rmu map preview` (non-strict), unresolved cells appear as the existing `<<unresolved>>` markers, and their count is shown.
2. **Given** a draft that still has T2/T3 routes or unresolved ValueMap pins, **When** the analyst attempts approval, **Then** approval is refused with the same reasons `check_approval` gives the CLI, shown verbatim.
3. **Given** a draft that passes the gate, **When** the analyst approves (with approver identity), **Then** a versioned Transform row is stored identical to the CLI result for the same draft, and the session records the same status/decision updates the CLI records.

---

### User Story 3 - Link detail and value mapping (Priority: P3)

As the analyst, clicking a drawn link opens its detail: the observed source values from the exemplar, and — when source and target vocabularies differ (e.g. source severity 1–10 vs target priority P1–P5) — an editable value map right at the link level: source_value → target_value entries with provenance (human / ai-accepted), AI-suggested entries clearly marked until accepted, unmapped observed values conspicuous. Edits stage in the session's draft value-map file; an explicit "Register & pin" action creates the new append-only ValueMap version and pins it on the route. The detail view also covers the other route mechanisms the transform already supports: constants, formulas (the existing closed function grammar), and per-batch prompt fields.

**Why this priority**: Vocabulary translation is where most human judgement lives; doing it at the link with observed values in view is the studio's biggest usability win after the canvas itself. Depends on US1.

**Independent Test**: Open a link whose source column has a small observed vocabulary, add one human entry and accept one AI-suggested entry, save, and verify via CLI that a new ValueMap version exists with correct provenance per entry and that the route pins that exact name@version.

**Acceptance Scenarios**:

1. **Given** a drawn link, **When** the analyst opens its detail, **Then** the exemplar's observed values for that source element are listed, and any observed value with no mapping entry is conspicuous.
2. **Given** value-map edits including AI-suggested entries, **When** the analyst saves, **Then** the entries are staged in the session's draft value-map file (no registry write); **When** the analyst triggers "Register & pin", **Then** a new append-only ValueMap version is registered (never mutating a prior version), each entry carries the correct provenance (`human` or `ai-accepted`), and the route's pin is updated to the new name@version.
3. **Given** a target field that needs a constant, formula, or per-batch prompt, **When** the analyst configures it in the detail view, **Then** the draft gains exactly the construct the transform schema already defines (constants map, closed-grammar formula, prompt with key/label/required), answerable at batch time the same way as today.

---

### User Story 4 - Visual onboarding review (Priority: P4)

As the analyst, I review draft OnboardingProposals (profile and template kinds) visually: the exemplar/target PDF renders as pages; spatially-anchored elements (overlay regions including grid-cell fallback regions, record-table column ranges and row bands, image regions) are drawn as selectable overlays on the pages; non-spatial elements (fingerprint anchors, furniture lines, header-field label strategies, cardinality) are listed alongside with their evidence and confidence. For each element I confirm, correct (edit the payload — e.g. rename a grid region), or remove. Approving runs verify-on-approve; on failure the persisted verify report is shown per-check.

**Why this priority**: Onboarding review is the second-heaviest human task and gains the most from overlays (e.g. the real Eskom holdout produced 373 proposed grid regions that must be reviewed and renamed). Independent of the mapping-canvas stories.

**Independent Test**: Create a draft template proposal via `rmu onboard draft-template` on a seed target, review it entirely in the studio (confirm/correct/remove elements, including renaming an overlay region), approve, and verify the registered TargetTemplate matches what the YAML+CLI flow would register from the same decisions.

**Acceptance Scenarios**:

1. **Given** a draft proposal with spatial elements, **When** the analyst opens it, **Then** each spatially-anchored element is drawn on the correct page at its registered coordinates (correct on rotated pages), and selecting an overlay selects its element; non-spatial elements appear in an adjacent list with evidence, confidence, and flags.
2. **Given** an element under review, **When** the analyst confirms, corrects (with edited payload), or removes it, **Then** the proposal records exactly the same review-state and corrected-payload the YAML workflow writes, so review can continue from the CLI at any point.
3. **Given** a proposal with any element still unreviewed, **When** the analyst attempts approval, **Then** approval is blocked naming the pending elements (same rule as today).
4. **Given** verify-on-approve fails, **Then** the persisted verify report is shown per-check (which exemplar, which check, expected vs got) and the proposal remains draft; **Given** it passes, **Then** the same registry row is created as via CLI approval.

---

### User Story 5 - Start new work from the studio (Priority: P5)

As the analyst, I can initiate work without dropping to the CLI: start a mapping session by choosing a registered profile@version, template@version and an exemplar file (assist mode defaulting per the existing resolution — local by default, manual always available, external offered only where client consent exists, otherwise the consent requirement is explained, not bypassed); and create onboarding drafts by supplying exemplar/target PDFs, including the seeded drift-reonboarding path.

**Why this priority**: Removes the last required CLI trip for the everyday flow, but everything it does is already reachable via CLI, so it can ship after the review/approve surfaces.

**Independent Test**: From the studio, start a session on a seed exemplar and create a draft-profile from seed exemplars; verify the resulting session and proposal rows/draft files are indistinguishable from CLI-created ones.

**Acceptance Scenarios**:

1. **Given** registered profiles and templates, **When** the analyst starts a session from the studio, **Then** the created session, draft transform and starter value-map files are identical to what `rmu map start` produces for the same inputs, and the assist mode is resolved by the existing precedence.
2. **Given** an exemplar whose fingerprint does not match the chosen profile, **When** the analyst starts a session, **Then** the studio surfaces the same drift block (and message) the CLI gives, and no session is created.
3. **Given** an unsupported PDF (scanned, encrypted, XFA, kind misuse), **When** the analyst submits it for onboarding, **Then** the studio shows the same named rejection and workaround the CLI prints.
4. **Given** a client without external-consent, **When** the analyst requests external assist, **Then** the studio explains the consent requirement and does not proceed externally.

---

### User Story 6 - Dashboard and registries (Priority: P6)

As the analyst, I open the studio and see the state of the whole utility: registered SourceProfiles, TargetTemplates, Transforms and ValueMaps (versions, effective dates), draft/approved/abandoned MappingSessions and OnboardingProposals, and recent ApplyRuns with their SafeCard batch verdict (pass/warn/block), per-document verdicts, tier/value coverage, and each run's exceptions report. From here I open any draft, abandon a draft session or proposal, and see local-AI health (the ai-doctor report) plus per-client external-consent status with grant/revoke.

**Why this priority**: Navigation and situational awareness — valuable, but every fact it shows exists via CLI listings today.

**Independent Test**: Seed the registries, run one batch via CLI, open the dashboard, and verify every registry row, session, proposal, and the run's SafeCard verdicts and exceptions are visible and match `rmu ... list` / `rmu runs show` output; abandon a draft and verify the CLI sees the same terminal state.

**Acceptance Scenarios**:

1. **Given** registered artifacts and past runs, **When** the analyst opens the dashboard, **Then** all registries, sessions, proposals and runs are listed with versions/status, and each ApplyRun shows its SafeCard verdicts, coverage figures and exceptions report content.
2. **Given** a draft session or proposal, **When** the analyst abandons it, **Then** the same terminal transition occurs as via the CLI, and approved/registered artifacts offer no mutating actions at all.
3. **Given** the AI layer in any state, **When** the analyst views AI health, **Then** the existing doctor report (embeddings, local LLM, degraded state) is shown; consent grant/revoke records exactly what the CLI consent commands record (who, when, note).

---

### User Story 7 - Locality and deletability (Priority: P7)

As the owner, the studio binds to localhost only and refuses non-loopback connections; it is single-user with no auth machinery; no document data persists browser-side beyond the session. It is an alternative front-end, not a fork: no pipeline, mapping, onboarding, apply or render module may import it, and removing the studio package leaves every existing capability and the full test suite green.

**Why this priority**: These are non-negotiable constraints on every other story (enforced from the first line of code via FRs below); as an independently *testable journey* it ranks last only because it delivers no analyst-facing capability by itself.

**Independent Test**: Attempt a connection from a non-loopback address and verify refusal; delete/exclude the studio package and run the full existing test suite green.

**Acceptance Scenarios**:

1. **Given** the studio is running, **When** a request arrives from a non-loopback address, **Then** it is refused (same loopback rule the local AI layer enforces for its LLM host).
2. **Given** the studio package is removed, **When** the full existing test suite runs, **Then** it passes, and every CLI capability remains intact.
3. **Given** any studio-driven change, **Then** it is one of the existing lifecycle transitions — nothing mutates an approved/registered artifact (Constitution III), and no AI is invoked anywhere the architecture forbids it (assist providers only; never at preview or apply — Constitution II).

---

### Edge Cases

- **Concurrent edits across surfaces**: the draft YAML is edited via CLI/editor while the studio has the session open — the studio blocks the conflicting save, shows what changed, and the analyst chooses reload-or-overwrite (FR-005). Same for onboarding drafts (which already re-sync YAML→DB on load).
- **Terminal-state drafts**: opening an approved or abandoned session/proposal shows a read-only view; all mutating actions are absent (FR-006).
- **Rotated pages**: overlays and highlights must land correctly on pages displayed via rotation — element coordinates are registered in rotation-aware visual space (the Eskom holdout is portrait-mediabox-displayed-landscape).
- **Very large proposals**: a proposal with hundreds of spatial elements (373 grid regions over 4 pages is a real case) must remain reviewable — selection, filtering by state/flags, and bulk confirm of unedited elements keep review tractable (FR-034).
- **Degraded local AI**: embeddings or the local LLM unavailable — session proceeds, the degraded state is shown (same assist-stats the CLI records), and manual mapping is unaffected.
- **No spatial anchor**: extraction-inventory elements without page coordinates (derived or positional fields) fall back to a listed panel on the source side rather than being invisible.
- **Racing approvals**: approval attempted in the studio after the same draft was approved via CLI (or vice versa) — the second attempt is refused by the same gate, never double-registering.
- **Browser closed mid-session**: no work is lost beyond the in-flight unsaved action — all draft state lives server-side in the same files/rows the CLI uses; the browser holds no document data afterwards (FR-043).
- **Oversized/unrenderable values in preview**: preview surfaces the same render problems (oversize value, missing image, round-trip mismatch) the CLI path reports, never truncating or silently absorbing.
- **Structureless proposal**: a proposal whose analysis found no elements carries only a diagnosis — the studio shows the diagnosis (what was searched, what was found, notes) with abandon as the primary action, never an empty review screen.
- **Database busy**: a CLI batch or migration holding the database when the studio writes — the studio surfaces a retryable "busy" state and never partially applies an action.
- **Studio URL reuse**: a stale URL (previous launch's secret, per FR-040a) is refused with a hint to restart via `rmu studio`; secrets are per-launch and never persisted to disk.

## Requirements *(mandatory)*

### Functional Requirements

**Surface parity and shared artifacts**

- **FR-001**: Every studio action MUST execute through the same code paths as its CLI equivalent (session build/regenerate, draft parsing/validation, approval gates, verify-on-approve, registry writes) and produce identical stored artifacts; the studio owns zero business logic (D6).
- **FR-002**: A draft mapping session or onboarding proposal started or part-edited on either surface MUST be readable and finishable on the other, because both operate on the same draft files and database rows.
- **FR-003**: The stored Transform produced by a studio-approved session MUST be schema-valid and identical to the CLI result for the same draft content (same routes, tiers, pins, prompts; identical stored transform text given identical decisions).
- **FR-004**: The studio MUST NOT keep studio-private mapping state: no shadow copies of routes, value maps, elements or decisions outside the existing draft files and rows.
- **FR-005**: Before persisting any edit, the studio MUST detect that the underlying draft changed since it was loaded (either surface); on conflict it MUST block the save, show what changed underneath, and let the analyst explicitly choose "reload latest (discard in-flight edit)" or "overwrite with mine" — never silently merging or silently losing either side.
- **FR-006**: Approved and abandoned sessions/proposals and all registered artifacts MUST be strictly read-only in the studio; new versions arise only through the existing versioning flows (Constitution III).

**Visual mapping canvas**

- **FR-010**: The studio MUST render the source exemplar and the target format side by side as their actual pages, with independent multi-page navigation on each side. The full document is always available — every page, including image-only pages — rendered lazily on demand, with navigation aids (jump-to-element, page indicators) so element-bearing pages are one action away on image-heavy exports.
- **FR-011**: Every element of the exemplar's extraction inventory MUST be visibly anchored: highlighted at its page location when it has coordinates, listed in a source panel when it does not; record-table columns MUST show a sample of observed values.
- **FR-012**: PDF targets MUST render with their registered fields/regions highlighted at their registered (rotation-aware) coordinates; CSV and docx targets MUST present their required target fields as a structured panel.
- **FR-013**: Selecting a source element then a target field MUST create a route in the draft transform at a human-confirmed tier and draw a persistent visual link; selecting an existing link MUST allow re-routing or deletion, each recorded in the session decisions log with the existing action vocabulary (accepted/edited/rejected/manual).
- **FR-013a**: The human-confirmed tier is DERIVED from the route's mechanism per design §7 — T0 when fully deterministic (closed value map covering all observed values, constant, or closed-grammar formula), T1 otherwise — displayed to the analyst but never hand-picked; it recomputes when the mechanism changes (e.g. a value map is registered that closes the vocabulary).
- **FR-014**: AI-proposed routes (tier T2) MUST be visually distinct as pending; accepting promotes to the derived human-confirmed tier per FR-013a (the only path to an approvable state), rejecting removes the route; both record decisions identically to the CLI flow.
- **FR-015**: Required target fields without a route (T3/unrouted) MUST be conspicuous at all times; the tier colour language MUST match the existing review-sheet semantics.
- **FR-016**: No indicator shown to the analyst may present field-name overlap as confidence; structural-fit evidence is value-level only (Constitution V).

**Studio UX (brainstormed 2026-07-14)**

- **FR-017**: The studio frame is a persistent slim navigation rail (Dashboard, Sessions, Proposals, Runs, AI) beside a full-width workspace; application chrome is dark so rendered document pages are the bright focal surfaces, with tier colours as the only loud accent language.
- **FR-018**: Links render as focus wires with colour pairing: at rest, linked elements carry matching numbered tier-coloured tags on both documents plus a compact link list between the panes (unmapped required fields appear in it as red entries); the wire draws bold only for the hovered/selected link; selecting a source element, list row, or target field focuses the same link; the list is filterable by tier/state so canvases with many links stay navigable.
- **FR-019**: A persistent readiness bar shows the live approval-gate state (fields ready / T2 pending / T3 unmapped / value maps unregistered), computed by the same gate logic that decides approval — never a parallel calculation; activating it navigates to the next blocking item.

**Link detail and value mapping**

- **FR-020**: Opening a link MUST show the exemplar's observed values for its source element and make unmapped observed values conspicuous.
- **FR-021**: The analyst MUST be able to edit value-map entries at the link level (source_value → target_value with provenance human/ai-accepted; AI-suggested entries marked until accepted); saves stage entries in the session's draft value-map file, and a distinct "Register & pin" action MUST register the new append-only ValueMap version and pin its name@version on the route (no registry version is created per save iteration). For a map not seeded by a proposal, the studio suggests a name derived from the link (analyst-editable before registration).
- **FR-022**: The link detail MUST support the transform's other mechanisms as data the schema already defines: constants, formulas restricted to the existing closed function grammar, and per-batch prompt fields (key, label, required) answerable at batch time exactly as today.

**Preview and approval**

- **FR-030**: Preview MUST use the same non-strict resolve path as the CLI preview, rendering into the target's actual format with the existing unresolved-cell markers and a count of unresolved fields, and surfacing the same render problems the CLI reports.
- **FR-030a**: Preview display is native and honest: PDF previews render inline as pages; CSV previews render inline as a table; docx previews are offered as the actual output file to open locally, with the studio showing the unresolved count and per-field resolved values — the studio MUST NOT present an HTML approximation of a non-HTML target as if it were the output.
- **FR-031**: Studio approval MUST run the same approval gate as the CLI (refusing unrouted required fields, remaining T2/T3 routes, unresolved value-map pins) and display refusal reasons verbatim; on success it stores the same versioned Transform row with approver identity.

**Visual onboarding review**

- **FR-032**: Draft proposals MUST render their exemplar/target PDF as pages with spatially-anchored elements drawn as selectable overlays at their registered coordinates (correct under page rotation); non-spatial elements MUST be listed with evidence, confidence and flags.
- **FR-033**: Confirm/correct/remove actions MUST write exactly the review-state and corrected-payload the existing workflow writes, keeping CLI review interchangeable mid-proposal; approval MUST remain blocked while any element is unreviewed, naming the pending elements.
- **FR-034**: Reviewing proposals with hundreds of elements MUST stay tractable via PDF-first keyboard triage: the rendered page is the workspace, the current element is spotlighted on the page with its detail in a side rail, and single-key actions (confirm / rename / remove) auto-advance to the next element; filters by state/kind/flag and per-page bulk-confirm of unedited elements cover the long tail (each bulk action recorded per element, indistinguishable from individual confirmation).
- **FR-035**: Studio approval of a proposal MUST run verify-on-approve; failures MUST show the persisted verify report per-check (exemplar, check, detail) with the proposal remaining draft; successes register the same registry row as CLI approval.

**Initiation**

- **FR-036**: The analyst MUST be able to start a mapping session from the studio (choose registered profile@version, template@version, exemplar file supplied via browser upload — content-addressed storage makes the artifact identical to a CLI path-based start); the created session and draft files MUST be identical to the CLI result, with assist mode resolved by the existing precedence (local default; manual always available; external only with client consent — otherwise explained, not bypassed). Regenerating AI proposals is available in the session view with the same semantics and refusals as the CLI (refused on approved sessions; prior generation retained in assist history).
- **FR-037**: The analyst MUST be able to create onboarding drafts (profile from exemplars, template from a target PDF) from the studio, including the seeded drift-reonboarding path; all CLI rejections (unsupported PDF kinds with named workaround, fingerprint drift block, kind-misuse warnings) MUST surface with the same messages.

**Dashboard and maintenance**

- **FR-038**: The dashboard MUST list all registered SourceProfiles, TargetTemplates, Transforms and ValueMaps (versions, status, effective dates), all sessions and proposals by status, and recent ApplyRuns with SafeCard batch and per-document verdicts, tier/value coverage, and the run's exceptions report content.
- **FR-039**: The analyst MUST be able to abandon a draft session or proposal from the dashboard (same terminal transition as the CLI) and view local-AI health (the existing doctor report) and per-client external-consent status, with grant/revoke recording the same fields the CLI records.

**Locality, safety and deletability**

- **FR-040**: The studio is launched via a new `rmu studio` CLI subcommand that starts the local server and prints/opens the localhost URL; the server MUST bind to localhost only and refuse connections from non-loopback addresses (same loopback rule the local AI layer enforces).
- **FR-040a**: Loopback binding alone is not trusted: `rmu studio` MUST generate a per-launch secret embedded in the URL it prints/opens, every request MUST carry it, and the server MUST validate Host/Origin headers — so a hostile web page in the same browser (CSRF/DNS-rebinding) or another local user cannot drive studio actions. Requests failing these checks are refused.
- **FR-041**: The studio is single-user with no user accounts, login flow, or session management beyond the per-launch URL secret (FR-040a); it MUST NOT expose any remote-access affordance.
- **FR-042**: No pipeline stage, mapping, onboarding, apply or render module may import the studio; this MUST be enforced by an invariant test in the same pattern as the existing no-AI-in-apply invariant, and the full existing test suite MUST pass with the studio package absent.
- **FR-043**: The browser MUST NOT persist document data beyond the session; all state lives server-side in the existing files and rows.
- **FR-044**: The studio MUST NOT introduce AI anywhere the architecture forbids it: AI participates only through the existing assist providers in mapping/onboarding sessions, never at preview or apply (Constitution II), and external assist remains consent-gated per client (Constitution VII).

### Key Entities

- **Mapping link**: the studio's visual representation of an existing route in the draft transform — a projection, NOT a new stored entity; its lifecycle (create, accept, reject, re-route, delete) is entirely expressed as edits to the draft transform plus session decision entries.
- **Draft mapping session** *(existing)*: the session row plus its draft transform and starter value-map files; the shared editing surface both the CLI and studio operate on.
- **Onboarding proposal** *(existing)*: draft profile/template with reviewable elements (review-state, corrected payload, evidence, confidence, flags) and a persisted verify report on failed approval.
- **ValueMap version** *(existing)*: append-only vocabulary translation with per-entry provenance; routes pin an exact name@version.
- **Transform version** *(existing)*: the approved, versioned mapping artifact; identical regardless of which surface approved it.
- **ApplyRun + SafeCard** *(existing, read-only in studio)*: batch results with pass/warn/block verdicts, coverage figures and exceptions report.
- **Studio server**: the local, loopback-only process serving the UI; holds no domain state of its own.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The full acceptance journey — review and approve a draft profile, start a mapping session, accept ≥1 AI-proposed link, draw ≥1 manual link, create one link-level value map containing ≥1 human and ≥1 ai-accepted entry, define one per-batch prompt field, preview, approve — completes end-to-end in the studio with zero hand-edits of any YAML file.
- **SC-002**: A batch run executed from the CLI with the studio-built transform completes exactly as with a CLI-built transform expressing the same decisions; the stored transform texts are identical.
- **SC-003**: 100% of connection attempts from non-loopback addresses are refused.
- **SC-004**: With the studio package removed, the full existing test suite passes and every CLI command remains functional.
- **SC-005**: A draft session part-edited in the studio is finishable from the CLI (and vice versa) with no reconciliation steps and no lost edits, verified in both directions.
- **SC-006**: Every studio-driven state change corresponds to an existing lifecycle transition; an audit of a full studio session shows zero writes outside the existing draft files, session/proposal rows and append-only registries.
- **SC-007**: 100% of spatially-anchored highlights and overlays land on their registered coordinates across all pages of the seed and holdout documents, including rotated pages.
- **SC-008**: Reviewing the real grid-heavy holdout proposal (hundreds of regions) to fully-reviewed state takes an analyst under 30 minutes in the studio (versus hours of raw YAML editing today).
- **SC-009**: An analyst who has completed one CLI mapping session before can complete the P1 canvas journey in the studio unaided (no documentation lookup) on first attempt.
- **SC-010**: A session on a 100+-page image-heavy exemplar opens to an interactive canvas in under 5 seconds; subsequent page navigation renders on demand without blocking interaction.
- **SC-011**: 100% of studio requests lacking the per-launch secret or failing Host/Origin validation are refused (verified with simulated cross-origin and stale-URL requests).

## Out of Scope

- Multi-user operation, authentication, remote deployment or any non-loopback binding, and real-time collaboration.
- Triggering batch apply runs from the studio — viewing runs is in scope; running batches stays on the CLI (canonical for batch and automation).
- Editing approved/versioned artifacts other than by creating a new version through the existing flows.
- Any studio-only business logic or studio-private storage of mapping state.
- Replacing the CLI: both surfaces remain first-class; deleting the studio must leave the product whole.
- Stack choice: D6 records the intended stack; naming and justifying it belongs to plan.md, not this spec.

## Assumptions

- Decisions **D6** (Mapping Studio approved as primary HIL surface; studio owns zero business logic; CLI canonical for batch) and **D9** (build order: this is feature 004) govern this feature; this spec implements D6 rather than re-deciding it.
- Single local analyst on personal hardware (A5, A9); a modern desktop browser is available on the same machine.
- In-browser rendering of the seed/holdout PDFs at page level is feasible; where a target format has no page representation (CSV/docx), a structured field panel is an acceptable v1 stand-in for "seeing the target".
- The existing draft files and database rows remain the single source of truth for in-flight work; the studio adds no storage of its own.
- Assist-mode defaults follow the existing resolution (local default; manual always fully functional; external consent-gated) — the studio changes how assist output is *reviewed*, not how it is produced.
- Existing exception/refusal messages (drift block, unsupported-PDF ladder, approval refusals, verify reports) are reused verbatim as studio-facing text; no parallel message catalogue is created.

## Brainstorm Log

### Session 2026-07-14 (superspec brainstorm — UI/UX)

Focus: modern, intuitive UI/UX for the studio. Explored via visual companion mockups; resolved:

1. **Navigation paradigm**: workspace + persistent slim rail (Dashboard, Sessions, Proposals, Runs, AI); document-heavy screens get maximum space (→ FR-017).
2. **Link visualization**: focus wires + colour pairing — numbered tier-coloured tags at rest, compact link list between panes, wire drawn bold only on hover/selection, tri-directional selection; initially chose always-on wires, revised to focus wires for scale on Eskom-sized targets (→ FR-018).
3. **Visual direction**: dark graphite chrome; white document pages pop like a light table; tier colours are the accent language (→ FR-017).
4. **Approval guidance**: persistent readiness bar fed by the same gate logic as approval, click-to-next-blocking-item; never a parallel calculation (→ FR-019).
5. **Onboarding triage at scale**: PDF-first keyboard triage (confirm/rename/remove with auto-advance, spotlight on page, per-page bulk-confirm) chosen over table-first for the 373-region real case (→ FR-034).

### Session 2026-07-14 (superspec brainstorm, round 2 — security/scale/boundaries)

1. **Local attack surface**: loopback bind is not trusted by itself — per-launch secret in the printed URL + Host/Origin validation refuses CSRF/DNS-rebinding and other-local-user requests (→ FR-040a, SC-011, stale-URL edge case).
2. **Image-heavy exemplars**: source pane always offers the full document (all pages, lazily rendered) with jump-to-element aids — "relevant pages only" default rejected in favour of full document fidelity (→ FR-010, SC-010).
3. **Defaults folded without questions**: structureless proposals show their diagnosis with abandon as primary action; database-busy states surface as retryable and never partially apply; per-launch secrets are never persisted (→ Edge Cases).
