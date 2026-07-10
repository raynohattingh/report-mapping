# Feature Specification: Report-Mapping Utility v1 — Map Once, Convert Many (Weekend Slice)

**Feature Branch**: `001-report-mapping-v1`

**Created**: 2026-07-10

**Status**: Draft

**Input**: User description: "Build the weekend slice of a report-mapping utility for drone-inspection operators. Problem: operators receive inspection reports from platforms (e.g. Scopito) and must re-deliver the same findings in a client's mandated format; today they re-do that conversion by hand for every report. The product maps a source report shape to a target format ONCE — AI-assisted with a human approving every mapping decision — stores that mapping as a reusable versioned transform, then converts every subsequent report of the same shape automatically with zero human field decisions."

## Clarifications

### Session 2026-07-10

- Q: When a batch contains drifted/unrecognized documents alongside healthy same-shape documents, what does BLOCK apply to? → A: Per-document quarantine — drifted/unknown documents are individually blocked (no output is produced for them; they are prominently listed in the SafeCard and the exceptions report); the remaining healthy documents in the batch convert normally.
- Q: What does one batch run produce for the interim defect-CSV target? → A: One defect CSV per source report; a consolidated batch-level CSV is a later template/data addition, not part of this slice.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One-Time Human-Approved Mapping Session (Priority: P1)

As an analyst at a drone-inspection operator, I register a target format and run a
one-time mapping session against ONE exemplar source report. The tool proposes field
routes and value conversions — e.g. the source severity scale 1–5 to the target
priority vocabulary, and free-text issue labels to entries in a defect-code list —
each proposal carrying a confidence tier and a one-line rationale. I review a
side-by-side review sheet (exemplar values, proposal, rationale), accept/edit/reject
each proposal, fill every unmapped required target field with a constant, a formula,
or a per-batch prompt, verify a rendered preview of the exemplar in the target
format, and approve. Approval stores the mapping as Transform version 1. A fully
manual mode — no AI involvement at any point — must accomplish the same session and
produce a transform of identical form.

**Why this priority**: The stored, human-approved transform is the product's core
asset; nothing else (batch conversion, trust reporting) can exist or be tested
without it. The manual mode is the degradation floor: the session must never depend
on AI availability or data-sharing consent.

**Independent Test**: Can be fully tested by running a mapping session against one
bundled exemplar report and confirming an approved Transform v1 is stored, without
any batch conversion existing yet. The manual-mode variant is tested by running the
same session with AI disabled and confirming an equivalent approved transform
results.

**Acceptance Scenarios**:

1. **Given** a registered target format and one exemplar source report, **When** the
   analyst starts a mapping session, **Then** the tool presents a complete draft
   mapping — field routes, value conversions, constants, and a list of unmapped
   required target fields — where every proposal shows a confidence tier and a
   one-line rationale, and AI-suggested items are visually distinct from
   human-confirmed ones.
2. **Given** a draft mapping under review, **When** the analyst accepts, edits, or
   rejects each proposal, **Then** the tool records each decision, and no
   AI-suggested item can enter the approved transform without an explicit human
   decision.
3. **Given** a draft with unmapped required target fields, **When** the analyst
   attempts to approve, **Then** approval is refused until every required field has
   a source route, a constant, a formula, or a per-batch prompt.
4. **Given** a completed draft, **When** the analyst requests a preview, **Then** the
   tool renders the exemplar into the target format for visual verification before
   approval.
5. **Given** an approved session, **When** the analyst inspects stored mappings,
   **Then** Transform v1 exists with approval metadata (who, when) and is immediately
   usable for batch conversion.
6. **Given** AI assistance is disabled (or unavailable), **When** the analyst runs
   the same session manually, **Then** every step above is achievable and the stored
   transform has the same form as an AI-assisted one.

---

### User Story 2 - Zero-Decision Batch Conversion (Priority: P2)

As an analyst, I point the tool at a folder of source reports of the same shape as
the exemplar, and it converts the entire batch with zero human field decisions. The
outputs are the target-format files for each report, a structured defect CSV per
source report, and an
exceptions report listing every record it could NOT confidently convert and exactly
why — a value outside an approved conversion list is reported as an exception, never
silently guessed or defaulted.

**Why this priority**: Batch conversion is the payoff of the mapping investment —
"map one, convert hundreds" is the product's economic claim. It depends on US1's
stored transform, so it is second.

**Independent Test**: Can be fully tested by running a batch of same-shape reports
(the bundled real exemplars plus faithful synthetic fixtures) through an approved
transform and confirming outputs, defect CSV, and exceptions report appear with no
human prompt for any field decision.

**Acceptance Scenarios**:

1. **Given** an approved transform and a folder of ≥20 same-shape reports, **When**
   the analyst runs the batch, **Then** every report converts to the target format
   plus its own structured defect CSV with zero human field decisions.
2. **Given** a batch containing a record whose value falls outside an approved value
   conversion, **When** the batch runs, **Then** that record appears in the
   exceptions report with the failing value, the reason, and a suggested resolution —
   and the output never contains a guessed conversion for it.
3. **Given** any completed batch — even one with no failures, **When** the analyst
   inspects the results, **Then** an exceptions report exists (possibly listing zero
   exceptions); the batch is never silently "all fine".
4. **Given** a folder containing a report whose shape is not recognized, **When** the
   batch runs, **Then** that report is individually quarantined — routed to human
   attention as unrecognized, never converted by guesswork — while the remaining
   healthy reports in the batch convert normally.

---

### User Story 3 - Trustworthy, Reproducible, Regenerable Output (Priority: P3)

As the engineer responsible for delivered output, I can trust the tool: before a
batch is applied, a "SafeCard" verdict tells me pass / warn / block, computed from
value-level coverage and human-confirmed confidence tiers — never from field-name
overlap. A structurally drifted input (e.g. a source report whose layout changed) is
BLOCKED, not mis-converted. Re-running a batch reproduces byte-identical output
files (outputs embed no generation timestamps). Any past run is exactly regenerable
from its recorded input fingerprints, prompt answers, transform version, and
template version.

**Why this priority**: Trust guarantees are what make the output deliverable to a
client; they harden US1+US2 rather than standing alone, so they come third — but
their invariants are never cut under schedule pressure.

**Independent Test**: Can be fully tested by (a) running the same batch twice and
comparing output bytes, (b) submitting a deliberately structure-drifted fixture and
confirming a block verdict, and (c) regenerating a past run from its recorded
identifiers and comparing to the original output. All three are proven by automated
tests, not demonstration.

**Acceptance Scenarios**:

1. **Given** a pending batch, **When** the SafeCard verdict is computed, **Then** it
   reflects only value-level coverage, human-confirmed confidence tiers, and the
   batch's exception rate — field-name overlap is never shown or used as a trust
   signal.
2. **Given** a deliberately structure-drifted input inside a batch of otherwise
   healthy reports, **When** the batch is submitted for conversion, **Then** that
   document's verdict is BLOCK — it is quarantined with no target output, routed to
   human review as a suspected new source shape, and listed in both the SafeCard
   batch summary and the exceptions report — while the healthy documents convert
   normally.
3. **Given** a completed batch, **When** the identical batch is re-run with the same
   transform version and template version, **Then** the output files are
   byte-identical — outputs embed no generation timestamps, so the comparison is a
   straight file hash.
4. **Given** any past run, **When** regeneration is requested using its recorded
   input fingerprints, transform version, and template version, **Then** the original
   output content is reproduced exactly.
5. **Given** an approved transform or target format that is later revised, **When**
   the revision is stored, **Then** it becomes a new version with an effective date
   and the prior version remains intact and usable for regeneration.

---

### Edge Cases

- A source report's shape is not recognized at all → routed to human attention,
  never guessed at.
- A value at conversion time falls outside every approved value conversion → logged
  exception with reason and suggested resolution; never an on-the-fly guess.
- A required target field has no source equivalent at approval time → approval is
  blocked until the analyst supplies a constant, formula, or per-batch prompt.
- A source report matches the expected shape superficially but its extraction
  anchors are missing or moved (structural drift) → that document is BLOCKED and
  quarantined for human review; healthy documents in the same batch still convert.
- A structurally intact document whose declared totals (e.g. stated annotation
  count) disagree with the records actually extracted → BLOCKED as suspected
  drift; silent under-extraction never reaches the client output.
- A single garbled row inside a structurally intact document → per-record
  exception; the document still converts with the failure reported.
- The batch folder is empty or contains duplicates of the same document → duplicates
  detected by content fingerprint and converted once (the duplicate filenames noted
  in the exceptions report); an empty batch is reported as such, not treated as
  success.
- A batch run is interrupted mid-way → no completed audit record is written; a
  partial run is never mistakable for a completed one, and re-running from scratch
  is always safe (outputs are deterministic).
- A source report contains zero findings → converts to a valid, empty-findings
  target output, not an error.
- An analyst attempts to change an approved transform → the change becomes a new
  version; the approved original is never mutated or deleted.
- AI proposals exist but were never human-reviewed → they can never enter an
  approved transform; approval requires an explicit decision on every item.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST let an analyst register a target format as data
  (template plus required-field schema plus validation rules), versioned and
  effective-dated. Only the two INTERIM stand-in target formats exist this weekend;
  the real client-mandated formats arrive later as new versions, with no change to
  the conversion machinery (Constitution I, IV).
- **FR-002**: The system MUST recognize a known source report shape from the
  document itself and refuse to process unrecognized shapes silently — unknown
  shapes are routed to human attention (Constitution VI).
- **FR-003**: The system MUST extract from a recognized source report a typed set of
  records (report header plus findings) sufficient to populate the target format.
- **FR-004**: The system MUST run a mapping session against ONE exemplar report that
  produces a complete draft mapping: field routes, value conversions, constants, and
  the list of unmapped required target fields.
- **FR-005**: In an AI-assisted session, every AI proposal MUST carry a confidence
  tier and a one-line rationale, be persisted for review, and be visually distinct
  from human-confirmed decisions until accepted (Constitution V).
- **FR-006**: The system MUST provide a side-by-side review sheet showing exemplar
  values, each proposal, and its rationale, against which the analyst accepts,
  edits, or rejects every item.
- **FR-007**: The system MUST refuse transform approval while any required target
  field lacks a source route, constant, formula, or per-batch prompt, or while any
  AI proposal remains unreviewed (Constitution V: proposed-tier items never enter an
  approved transform). A "formula" is drawn from a closed, schema-validated set of
  named, pure, deterministic operations declared as data (e.g. concatenation,
  substring/pattern extraction, date reformatting, number formatting, arithmetic on
  extracted values) — never user-defined code, environment access, current time, or
  randomness; anything outside the set is rejected at validation (Constitution II,
  IV).
- **FR-008**: The system MUST render the exemplar into the target format for human
  verification before approval.
- **FR-009**: On approval, the system MUST store the mapping as a versioned,
  effective-dated transform with approval metadata (who, when); later revisions
  create new versions and never mutate or delete prior ones (Constitution III).
- **FR-010**: A fully manual mapping mode (no AI involvement) MUST accomplish the
  entire session end-to-end and produce a transform of identical form
  (Constitution VII).
- **FR-011**: Batch conversion MUST be deterministic: no AI, no network, no
  nondeterminism; same inputs + same transform version + same target-format version
  produce byte-identical output files (Constitution II). Rendered outputs embed NO
  generation timestamps: document metadata (created/modified) is pinned to a fixed
  value, and any date in content comes only from source data, the transform, or
  recorded batch inputs — so the determinism test is a straight file hash. Run
  timestamps live only in the audit record.
  When the transform declares per-batch prompt fields, their answers are supplied
  as explicit inputs at batch launch — the tool lists the required prompts and
  refuses to start without them; the run itself is never interactive. Prompt
  answers are batch-level inputs, not per-record field decisions, and count as
  part of "same inputs" for determinism.
- **FR-012**: A value falling outside an approved value conversion at batch time
  MUST become a logged exception carrying the record reference, failing value,
  reason, and suggested resolution — never a guess or silent default
  (Constitution II).
- **FR-013**: Every batch run MUST emit an exceptions report, even when there are
  zero exceptions (Constitution V).
- **FR-014**: Batch outputs MUST include, per source report, the target-format
  files and a structured defect CSV whose defect vocabulary is loaded from the
  bundled defect-code list as data, never hardcoded (Constitution IV). A
  consolidated batch-level CSV is out of scope for this slice (later template/data
  addition).
- **FR-015**: Before applying, the system MUST compute a SafeCard verdict — pass
  (apply), warn (apply with prominent exceptions), block (do not apply; route to
  human) — from value-level coverage, human-confirmed confidence tiers, and the
  exception rate only. The verdict is computed per document and summarized per
  batch: a blocked document is quarantined (FR-016) without blocking healthy
  documents. Field-name overlap MUST never appear as a trust signal
  (Constitution V).
- **FR-016**: A structurally drifted input MUST produce a per-document block: it is
  quarantined with no target output, routed to human review, and listed in both the
  SafeCard batch summary and the exceptions report (and the batch command signals
  "blocked" distinctly when every document blocks), never best-effort converted. Healthy
  documents in the same batch MUST still convert (Constitution V). Two integrity
  signals trigger the document-level block: (a) expected extraction anchors missing
  or relocated, and (b) the document's own declared totals (e.g. its stated
  annotation count) disagreeing with the number of records actually extracted —
  silent under-extraction is treated as drift, not tolerated. Record-level parse
  failures inside a structurally intact document (e.g. one garbled table row)
  remain per-record exceptions; the document still converts with the failures
  reported (FR-012).
- **FR-017**: The system MUST record every batch run as an audit record: input
  content fingerprints, per-batch prompt answers, transform version, target-format
  version, verdict, outputs manifest, and exceptions — sufficient to regenerate the
  run's output exactly on demand (Constitution III). Regeneration replays the
  recorded prompt answers; it never re-asks.
- **FR-018**: The system MUST provide a regeneration capability that reproduces any
  past run's output content exactly from its audit record.
- **FR-019**: Value conversions (e.g. severity → priority vocabulary, issue label →
  defect code) MUST be stored as named, versioned lookup lists with provenance per
  entry (human vs AI-accepted); additions create new versions (Constitution III).
  A transform version MUST reference each value map at an exact version (name +
  version, never "latest"): growing a value map creates a new value-map version and
  a new transform version that points to it, so the ApplyRun's recorded transform
  version transitively fixes every lookup used and regeneration needs no additional
  version bookkeeping.
- **FR-020**: The system MUST NOT send any real client report content to a
  third-party service; all AI assistance in this slice operates only on the bundled
  demo reports and synthetic fixtures (Constitution VII).
- **FR-021**: The mapping session MUST persist its full lineage — every AI proposal
  and every human decision with timestamps — as the audit trail of how the transform
  came to be.

### Key Entities

- **Source Profile**: A recognized source report shape (platform, export kind, job
  type, structural version) with its recognition fingerprint. This slice ships
  exactly one: the bundled Scopito powerline demo shape.
- **Target Template**: A registered target format — template files, required-field
  schema, validation rules — versioned, append-only, effective-dated. This slice
  ships two INTERIM stand-ins: a structure-inspection report pack and a structured
  defect CSV.
- **Transform**: The stored mapping for one (source profile, target template) pair:
  field routes, value-conversion references (each pinned to an exact value-map
  version), constants, exception rules. Versioned, append-only, with approval
  metadata.
- **ValueMap**: A named, versioned lookup (source value → target value) with
  per-entry provenance; referenced by transforms.
- **Mapping Session**: The recorded human-in-the-loop episode producing or revising
  a transform: AI proposals, human decisions, timestamps.
- **Source Document**: One received report: content fingerprint, original filename,
  recognized profile, extraction result reference.
- **Apply Run**: One batch execution's audit record: document fingerprints,
  per-batch prompt answers, transform version, template version, SafeCard verdict,
  outputs manifest, exceptions.
- **Exception**: One record-level conversion failure: what failed, why, suggested
  resolution, open/resolved status.
- **SafeCard Verdict**: The pre-apply trust report: per-field confidence tiers,
  value-level coverage, exception rate, and the pass/warn/block outcome.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From ONE bundled exemplar report, an analyst completes a mapping
  session — review, unmapped-field resolution, preview, approval — in at most 2
  hours of human time, producing stored Transform v1.
- **SC-002**: With one approved transform, a batch of at least 20 same-shape reports
  (the two bundled real demo reports plus faithful synthetic same-structure
  fixtures) converts with ZERO human field decisions; only exception handling may
  involve a human, and the exception rate is reported.
- **SC-003**: One deliberately structure-drifted fixture submitted within a batch of
  otherwise healthy reports is blocked and quarantined with a human-review routing
  while the healthy reports convert; zero drifted inputs are mis-converted.
- **SC-004**: Re-running any batch with the same inputs, transform version, and
  template version yields byte-identical output files, verified by straight file
  hash (outputs embed no generation timestamps) — proven by automated tests, not
  demonstration.
- **SC-005**: Any past batch run is regenerated exactly from its recorded audit
  record — proven by automated tests.
- **SC-006**: 100% of batch runs emit an exceptions report, including clean runs.
- **SC-007**: A fully manual (no-AI) mapping session completes end-to-end and
  produces an approved transform of identical form to an AI-assisted one.
- **SC-008**: No fabricated client-format content exists anywhere in the slice: both
  shipped target formats are clearly labeled INTERIM and are replaceable as data.

## Assumptions

Numbered assumptions and decisions below are maintained in `ASSUMPTIONS.md` at the
repo root; they are cited here by ID and were made deliberately on 2026-07-10 to
unblock this slice.

- **A1**: Current source-platform exports share the structure of the bundled 2020
  demo reports; a structural change is handled as a new source profile version (the
  drift-block path), not a defect.
- **A2**: The two INTERIM target formats are structurally representative of the real
  client-mandated formats, which will slot in later as new template versions without
  machinery changes.
- **A3**: The source severity vocabulary is exactly 1–5 plus "?" (point of
  interest), per the demo reports.
- **A4**: PDF is the source medium for this slice; a structured export, if the
  operator uses one, would be a better source and swaps in at the extraction layer
  only.
- **A5**: Single operator, single machine; no multi-user or hosted deployment.
- **A6**: AI assistance runs only in mapping sessions and only on demo/synthetic
  data until client data-processing consent exists; the manual mode is always fully
  functional.
- **A7**: This weekend slice = one source profile, two interim target formats, the
  full pipeline, and the invariant tests. Deferred, NOT dropped: a second source
  platform, the ≤2h human-setup benchmark measured with a real user, demo-script
  polish, extraction hardening beyond the demo PDFs and synthetic drift fixtures.
- **A8**: A technical analyst editing the draft mapping directly (with schema
  validation and the review sheet as guardrails) is acceptable for this slice; a
  friendlier review interface is a later, data-compatible addition (D1).
- Under schedule pressure the cut order is D3: AI assistance first, review-sheet
  polish second, the second interim target format third; determinism, append-only
  versioning, drift-block, exceptions reporting, and their tests are NEVER cut.

## Brainstorm Log

### Session 2026-07-10 — edge-case deep-dive

Five gaps surfaced by stress-testing the regeneration and determinism invariants;
all resolved with the recommended (most conservative, constitution-consistent)
option and folded into the sections noted:

1. **Value-map version pinning** — transforms reference value maps at exact
   versions (never "latest"); growing a value map creates a new value-map version
   and a new transform version, so the recorded transform version transitively
   fixes every lookup. → FR-019, Key Entities (Transform).
2. **Per-batch prompt answers** — supplied upfront at batch launch (run never
   interactive), recorded in the ApplyRun, replayed on regeneration; they are
   batch-level inputs, not field decisions. → FR-011, FR-017, Key Entities
   (Apply Run), US3 narrative.
3. **Formula semantics** — a closed, schema-validated set of pure deterministic
   operations declared as data; no user code, environment, time, or randomness.
   → FR-007.
4. **Partial extraction failure** — document-level block on integrity signals
   (anchors missing/relocated, or declared totals ≠ extracted count — silent
   under-extraction is drift); record-level parse failures stay per-record
   exceptions. → FR-016, Edge Cases.
5. **Timestamp discipline** — outputs embed no generation timestamps (metadata
   pinned); determinism test is a straight file hash; run times live only in the
   audit record. → FR-011, SC-004, US3.

Defaults folded without a question (low ambiguity): duplicates convert once and
are noted in the exceptions report; an interrupted run writes no completed audit
record. → Edge Cases.

## Out of Scope (deferred, not dropped)

- Any second source platform (e.g. Zeitview).
- The real client-mandated target formats (they arrive later as data — new template
  versions; never invented here, per Constitution I).
- Any web or graphical UI; multi-user or hosted/SaaS anything.
- Image classification, anomaly detection, or annotation tooling (v2 — separate
  design; none of it is built here).
- Portal integrations, flight planning, hosting platforms.
