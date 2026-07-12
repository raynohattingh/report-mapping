# Feature Specification: Local AI Assistance Layer

**Feature Branch**: `002-local-ai-assist`

**Created**: 2026-07-11

**Status**: Draft

**Input**: User description: "Add a local AI assistance layer to the mapping utility so that mapping sessions get intelligent proposals with ZERO network calls — enabling AI assistance on confidential client documents without any data leaving the machine."

## Clarifications

### Session 2026-07-11

- Q: When only some local assistance assets are available (e.g. embeddings installed, Ollama LLM not), how should a local-mode session degrade? → A: Per-tier degradation — embeddings-only still gives field-route ranking (no value-map proposals, with a clear message); fully manual only when no assets are installed (consistent with D8's optional tier 2).
- Q: How does a session know which client's data it is processing, for the external-mode consent gate? → A: Explicit per-session client identifier (CLI arg or session config) matched against owner-recorded consent entries; external mode with no identifier, or an identifier without a consent entry, refuses to run. Nothing is inferred.
- Q: Is embedding-based profile-fingerprint similarity (design §13.2's second tier-1 deliverable) in scope? → A: In scope, session/onboarding-side only — suggests which known profile a new document resembles during mapping/onboarding sessions; apply-time Detect remains deterministic and untouched.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Provably Offline Mapping Assistance (Priority: P1)

As an analyst running a mapping session on confidential client reports, I receive AI-proposed field routes and value-map suggestions while the network is physically unused, so I can demonstrate to a client that their data never left my machine.

**Why this priority**: This is the core promise of the feature — AI assistance without data leaving the machine. It unblocks using AI assistance on real client documents before (or without) per-client data-processing consent, which is currently forbidden by the project's data-sensitivity rule. Without this guarantee, none of the other stories deliver their intended value on confidential data.

**Independent Test**: Run a full mapping session in local mode inside a test harness that blocks all socket/network operations; the session completes with proposals produced and zero network I/O attempted.

**Acceptance Scenarios**:

1. **Given** assistance mode is set to `local` and all non-loopback network access is blocked at the socket level, **When** an analyst runs a complete mapping session on a seed fixture report, **Then** the session completes successfully with field-route and value-map proposals, and no non-loopback network operation is attempted.
2. **Given** assistance mode is set to `local`, **When** any component of the mapping session attempts a non-loopback network call, **Then** the attempt is treated as a defect (test failure), not silently tolerated.
3. **Given** a completed local-mode mapping session, **When** the analyst reviews the session record, **Then** the record shows which assistance mode produced each proposal, supporting the claim that data stayed on the machine.

---

### User Story 2 - Ranked Candidate Target Fields (Priority: P2)

As an analyst mapping a new source shape, for each source field I see candidate target fields ranked by semantic similarity (e.g. "Severity" ranks near "Priority/Urgency", "Comments" near "Defect description"), so I pick from a shortlist instead of searching the full target schema; the true match is almost always in the top few candidates.

**Why this priority**: Ranking is the highest-leverage time-saver in the human-in-the-loop session and directly supports the ≤2h human setup goal. It is useful even before value-level proposals exist.

**Independent Test**: On the bundled seed fixtures with human-confirmed routes as ground truth, measure the rank of each correct target field in the produced candidate list.

**Acceptance Scenarios**:

1. **Given** a source field named "Severity" and a target schema containing "Priority/Urgency" among other fields, **When** candidates are ranked, **Then** "Priority/Urgency" appears in the top candidates.
2. **Given** the seed fixture source profiles and their human-confirmed field routes, **When** candidate ranking runs for every routed source field, **Then** the correct target field appears in the top 3 candidates for at least 90% of fields.
3. **Given** a source field with no plausible target match, **When** candidates are ranked, **Then** the analyst can still see the shortlist is weak and choose "no route" — ranking never forces a selection.

---

### User Story 3 - Locally Produced ValueMap Proposals with Rationales (Priority: P3)

As an analyst handling value-level conversions (severity scales, code vocabularies, units, dates, free-text to enum), I receive proposed ValueMap entries each with a one-line rationale, produced entirely locally; every proposal lands in the existing review flow and nothing is auto-accepted.

**Why this priority**: Value-level mapping is the most error-prone and time-consuming part of the session, but it depends on the local assistance foundation (US1) and is complementary to field routing (US2).

**Independent Test**: Run value-map proposal generation on seed fixture vocabularies in local mode and verify each proposal carries a rationale, enters the review flow unaccepted, and malformed proposals are dropped.

**Acceptance Scenarios**:

1. **Given** a source severity scale and a target severity vocabulary, **When** local proposal generation runs, **Then** proposed ValueMap entries are produced, each with a one-line rationale.
2. **Given** any generated proposal, **When** it enters the mapping session, **Then** it appears in the human review flow as unconfirmed — no proposal is ever auto-accepted.
3. **Given** the local model emits output that does not conform to the strict proposal schema, **When** validation runs, **Then** the malformed output is dropped and never surfaced as a trusted proposal, while the session summary reflects it in the aggregate dropped count.

---

### User Story 4 - Owner-Controlled Assistance Modes (Priority: P2)

As the owner, I choose the assistance mode in configuration: `none` (fully manual — must remain fully functional), `local` (default), or `external` (external API, only with an explicit per-client consent flag recorded in config); switching modes changes no stored artifact formats and no pipeline behaviour outside the mapping session.

**Why this priority**: Mode control is the safety and compliance boundary of the whole feature — `none` preserves the guaranteed manual path, and the consent gate on `external` enforces the data-sensitivity rule. It is small but must exist before local assistance ships as the default.

**Independent Test**: Run the mapping session under each of the three modes (and external without consent) and compare stored artifacts and pipeline behaviour.

**Acceptance Scenarios**:

1. **Given** assistance mode `none`, **When** an analyst runs a mapping session, **Then** the session is fully functional with no AI proposals — the manual path works end to end.
2. **Given** assistance mode `external` with no recorded per-client consent flag, **When** a mapping session starts, **Then** the session refuses to run in external mode and tells the owner why.
3. **Given** assistance mode `external` with an explicit per-client consent flag recorded in config, **When** a mapping session runs, **Then** external assistance is permitted for that client only.
4. **Given** the same mapping decisions confirmed under any mode, **When** transforms, ValueMaps, and session artifacts are stored, **Then** their formats are identical across modes — mode changes nothing about stored artifact shapes.
5. **Given** any assistance mode, **When** apply, validate, render, or audit stages run, **Then** their behaviour is unchanged — assistance exists only inside the mapping session.

---

### Edge Cases

- Local assistance assets partially installed: degradation is per tier — embeddings without the local language model gives ranking only (no value-map proposals, clear message); no assets at all gives the manual (`none`-equivalent) experience. Never crash, and never silently emit empty rankings presented as meaningful.
- Local model produces output that is schema-valid but semantically unresolvable (e.g. proposes a route to a nonexistent target field): proposals referencing unknown fields or values must be dropped at validation, same as malformed output.
- Target schema is very large or very small (e.g. 2 fields): ranking must still behave sensibly — shortlist size adapts and never pads with meaningless candidates presented as strong.
- Source field names are cryptic or non-English abbreviations: ranking may be weak; the analyst must be able to see and override — weak similarity must never be dressed up as confidence (constitution rule 5).
- Consent flag exists for client A but the session is run for client B in external mode: refusal — consent is per-client.
- Mode is switched mid-project between sessions: previously stored transforms and ValueMaps remain valid and re-applicable; only future proposal generation changes.
- Two candidates tie or near-tie in similarity: ordering must be deterministic across runs on the same machine and assets, so review sheets are reproducible.
- Local model or embedding assets are upgraded mid-review: persisted proposals under review do not change (FR-016); only an explicit regeneration produces a new set, and the provenance record reflects it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The mapping session MUST support three assistance modes selected in configuration: `none`, `local` (default), and `external`.
- **FR-002**: In `local` mode, the mapping session MUST perform zero non-loopback network I/O end to end; all proposal generation (field-route ranking and value-map proposals) runs on the local machine. Loopback traffic (127.0.0.1/::1) to a local model runtime is permitted, and the session MUST verify that runtime is bound to localhost only. The guarantee is stated precisely as "no data leaves the machine".
- **FR-003**: In `none` mode, the mapping session MUST remain fully functional as a purely manual flow with no AI involvement.
- **FR-004**: In `external` mode, the session MUST refuse to run unless an explicit per-client consent flag is recorded in configuration for the client whose data is being processed. Client identity is supplied explicitly per session (invocation argument or session configuration) and matched against owner-recorded consent entries; a missing client identifier, or one without a matching consent entry, refuses external mode. Client identity is never inferred.
- **FR-005**: For each source field, the system MUST produce a ranked shortlist of candidate target fields ordered by semantic similarity to the source field (name plus available descriptive context).
- **FR-006**: For value-level conversions (severity scales, code vocabularies, units, dates, free-text to enum), the system MUST produce proposed ValueMap entries, each carrying a one-line rationale.
- **FR-007**: Every AI-generated proposal (route or ValueMap entry) MUST enter the existing human review flow as unconfirmed; no proposal is ever auto-accepted.
- **FR-008**: All locally generated proposals MUST be validated against a strict schema before entering the session; malformed or unresolvable outputs (unknown fields, unknown values) MUST be dropped and never surfaced as trusted proposals. Individual dropped outputs are invisible to the analyst, but the session summary/review sheet MUST always report aggregate counts (proposals shown vs dropped as invalid) so degraded model health is observable.
- **FR-009**: Assistance mode MUST NOT change the format of any stored artifact (transforms, ValueMaps, session records, review sheets) — artifacts produced under different modes are structurally identical.
- **FR-010**: Assistance MUST exist only within the mapping session; apply, validate, render, and audit behaviour is unchanged in all modes, and existing determinism tests pass untouched.
- **FR-011**: Local assistance MUST degrade gracefully per tier: if the local language model is unavailable but embeddings are installed, field-route ranking still works and only value-map proposal generation is disabled (with a clear message); only when no local assets are installed does the session fall back to the fully manual experience. Missing assets never cause a session failure.
- **FR-012**: Candidate ranking output MUST be deterministic for the same inputs on the same machine and installed assets, so review sheets are reproducible.
- **FR-013**: Session records MUST identify which assistance mode (none/local/external provenance) produced each proposal.
- **FR-014**: Setup of local assistance assets MUST be a documented manual procedure; the system does not automate model downloads.
- **FR-015**: Within mapping/onboarding sessions, the system MUST offer profile-fingerprint similarity: given a new document's structural fingerprint, suggest which known source profiles it most resembles, as a ranked suggestion for the analyst. This is session-side assistance only — apply-time profile detection remains deterministic and unchanged.
- **FR-016**: Proposals are generated once per mapping session and persisted as session artifacts (with provenance per FR-013); the review flow always reads the persisted set, so re-opening a session never silently changes what is under review. Regenerating proposals is an explicit analyst action that replaces the persisted set visibly.

### Key Entities

- **Assistance Mode**: A configuration value (`none` | `local` | `external`) governing how proposals are generated in the mapping session; `local` is the default.
- **Consent Flag**: A per-client record in configuration explicitly authorizing external API use for that client's data; absence means external mode refuses to run. Matched against an explicit per-session client identifier — never inferred.
- **Candidate Ranking**: An ordered shortlist of target fields for a given source field, with similarity-based ordering; input to the analyst's route decision, never a decision itself.
- **Proposal**: An AI-suggested field route or ValueMap entry (with one-line rationale), schema-validated, provenance-tagged with its assistance mode, and always unconfirmed until human review.
- **Local Assistance Assets**: The locally installed model/embedding resources that proposal generation depends on; their absence triggers per-tier graceful degradation.
- **Profile Fingerprint Similarity**: A session-side suggestion ranking known source profiles by structural resemblance to a new document; an onboarding aid only, never used by apply-time detection.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A repeatable test proves a complete mapping session in `local` mode performs zero non-loopback network I/O (all non-loopback socket operations blocked; session still succeeds), with a companion check that any local model runtime is bound to localhost only.
- **SC-002**: On the bundled seed fixtures, the correct target field appears in the top 3 ranked candidates for at least 90% of source fields that have a human-confirmed route.
- **SC-003**: 100% of malformed or unresolvable local proposals are dropped before reaching the analyst; zero malformed proposals appear in any review sheet.
- **SC-004**: Existing apply-time determinism tests pass without modification after the feature lands.
- **SC-005**: A mapping session in `external` mode with no recorded per-client consent flag refuses to run 100% of the time, with an explanatory message.
- **SC-006**: A mapping session in `none` mode completes end to end with zero AI involvement, producing artifacts structurally identical to those from assisted sessions.
- **SC-007**: In a seed-fixture mapping session, the analyst selects field routes from the ranked shortlist (rather than searching the full target schema) for the large majority of fields, reducing per-field decision effort.
- **SC-008**: All local proposal generation for one exemplar report (rankings, value-map proposals, fingerprint suggestions) completes within 5 minutes on the reference machine (A9: CPU-only Apple-silicon, ≥16GB), presented as one visible step with progress feedback; consulting already-generated rankings during review feels instant (<1 second).

## Assumptions

- The seed fixtures with human-confirmed routes (produced during v1 milestone M3 mapping sessions on the bundled Scopito demo exports) serve as the ground-truth dataset for the 90% top-3 ranking criterion.
- "Zero network I/O" is scoped to the mapping session process while it runs; unrelated background OS traffic is out of scope of the guarantee and of the test.
- The local machine is a personal CPU-capable workstation; acceptable local models run on CPU (GPU-only models are explicitly out of scope).
- The existing review flow (CLI + YAML + HTML review sheet, per decision D1) is the review surface for all proposals; this feature feeds it, not replaces it.
- The consent flag is a deliberate, owner-recorded configuration entry per client — no in-session prompt can create it.
- `local` is the default assistance mode; on a machine without installed assets, behaviour follows the graceful-degradation path (FR-011), which is experientially equivalent to `none`.
- Dropping of malformed local-model outputs (FR-008) hides the individual outputs from the analyst, never the fact of dropping: aggregate counts always appear in the session summary, and full outputs may be logged for diagnostics.
- Out of scope: any AI at apply time (constitution rule 2), model fine-tuning, GPU-only models, and automated model downloading beyond documented setup steps.

## Brainstorm Log

### Session 2026-07-11 (edge-case deep dive)

- **Loopback boundary**: "zero network I/O" refined to zero *non-loopback* I/O — a local model runtime (Ollama, per D8) serves over localhost HTTP, so the socket-blocking test permits 127.0.0.1/::1 and a companion check asserts the runtime binds to localhost only. Claim stated precisely as "no data leaves the machine". (FR-002, SC-001, US1 scenarios.)
- **Proposal persistence**: proposals are generated once per session and persisted with provenance; review always reads the persisted set, so asset upgrades mid-review never silently change the sheet. Regeneration is an explicit, visible analyst action. (New FR-016, new edge case.)
- **Drop observability**: individual malformed model outputs stay invisible, but aggregate shown-vs-dropped counts always appear in the session summary so a degraded local model is distinguishable from "few suggestions available". (FR-008, US3 scenario 3, Assumptions.)
- **Performance budget**: all local generation for one exemplar completes ≤5 minutes on the A9 reference machine as one visible step with progress; consulting generated rankings feels instant. (New SC-008.)
- Categories reviewed without spec changes: security/privacy (covered by the feature's own consent gate + rule 7; diagnostic logs are local-only), scale (single-operator per A5), UX confusion points (weak-shortlist and tiny-schema edge cases already present).
