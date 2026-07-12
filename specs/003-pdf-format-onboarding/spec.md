# Feature Specification: AI-Assisted Onboarding of New PDF Source Shapes and Target Formats

**Feature Branch**: `003-pdf-format-onboarding`

**Created**: 2026-07-12

**Status**: Draft

**Input**: User description: "Add AI assisted onboarding of NEW source report shapes and NEW target formats from PDFs, so that adding a format the tool has never seen takes minutes of human validation instead of hand-building extraction recipes or templates — while keeping the rule that nothing unvalidated ever converts real data."

## Clarifications

### Session 2026-07-12

- Q: How should the analyst review and correct a draft proposal before approving it? → A: Same pattern as the existing mapping session (decision D1): the proposal is persisted as an editable document, a generated visual review sheet renders each proposed element against the actual PDF for eyeballing, and approval is an explicit separate command.
- Q: What powers the document analysis that generates draft proposals? → A: Deterministic structural heuristics always produce the base proposal; the existing local AI assistance layer (feature 002) optionally enriches it (field naming, label matching, confidence hints). Fully offline-capable; `--no-ai` yields heuristics-only proposals; no cloud AI in onboarding.
- Q: What is the output cardinality when rendering a batch into a PDF target? → A: Each registered TargetTemplate declares its own cardinality as data: per-record (one filled PDF per record, e.g. Annexure-style per-defect forms) or per-batch (one PDF for the whole batch). Per-record is the primary case implemented first.
- Q: Where does the held-out acceptance fixture for SC-001 come from? → A: Rayno will provide an additional real demo report (Zeitview) in `seed/`. It is quarantined: never opened, inspected, or used by any development or tuning activity — reserved exclusively for the SC-001 acceptance measurement.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Onboard a new source report shape from a PDF (Priority: P1)

An analyst receives a structured source report PDF that the tool does not recognise (no registered profile matches). They run a draft-profile command. The tool analyses the document — repeating structures, tables, header/label blocks, page anatomy — and proposes a draft extraction recipe: which header fields exist, where the record rows live, what columns/labels they carry, each element carrying a per-element confidence score. The analyst reviews the proposal against the actual PDF, corrects or confirms each element, and approves it. Approval registers a new versioned SourceProfile that from then on extracts this shape deterministically, exactly like a hand-built profile.

**Why this priority**: This is the core value of the feature — every new client or export variant currently means hand-building an extraction recipe. Cutting that to minutes of validation is the headline outcome, and it is independently useful even if target-side onboarding never ships.

**Independent Test**: Run the draft-profile command against a held-out structured PDF fixture never used during development; measure the proposal's record-extraction accuracy before correction, then approve a corrected version and verify subsequent extraction of that shape is deterministic and correct.

**Acceptance Scenarios**:

1. **Given** a structured source PDF with no matching registered profile, **When** the analyst runs the draft-profile command, **Then** the tool produces a draft extraction recipe proposing header fields, record-row locations, and column/label assignments, each with a per-element confidence score.
2. **Given** a draft profile proposal, **When** the analyst reviews it against the actual PDF, **Then** they can confirm, correct, or reject each proposed element individually before approval.
3. **Given** an analyst-corrected draft proposal, **When** the analyst approves it, **Then** a new versioned SourceProfile (v1) is registered, and re-running extraction on the exemplar PDF with that profile yields the human-validated records with no AI involvement.
4. **Given** a registered (approved) profile created this way, **When** further same-shape PDFs are processed, **Then** they are detected and extracted deterministically — same input always yields identical records.
5. **Given** a held-out structured PDF fixture never used in development, **When** a draft proposal is generated, **Then** at least 80% of its records are extracted correctly before any human correction, and 100% of the human-validated subset extract correctly after approval.

---

### User Story 2 - Drafts can never touch real conversions (Priority: P2)

The owner needs the safety property that underpins the whole feature: a draft is a distinct artifact status. A draft profile or draft template can never be referenced by a batch ApplyRun — only human-approved v1+ artifacts can. Approval records who approved and when. Everything remains data: a registered profile or template is stored configuration, not generated code.

**Why this priority**: Without this gate, AI-proposed artifacts could silently convert real data before a human has validated them — the exact failure mode the product promise ("nothing unvalidated ever converts real data") exists to prevent. It must land with, not after, the first onboarding path.

**Independent Test**: Create a draft artifact of each kind, attempt an ApplyRun that references it, and verify the run fails with a clear error before any record is converted; approve the artifact and verify the same run then proceeds.

**Acceptance Scenarios**:

1. **Given** a draft profile or draft template, **When** any batch ApplyRun attempts to reference it, **Then** the run fails before converting anything, with a clear error naming the draft artifact and its status.
2. **Given** a draft artifact, **When** an analyst approves it, **Then** the registered artifact records who approved it and when, and becomes version 1 of a versioned, append-only, effective-dated registry entry.
3. **Given** an approved profile or template, **When** it is inspected, **Then** it is stored configuration data (human-readable, schema-validated) — not generated code — and revising it produces a new version rather than mutating the old one.
4. **Given** the existing registered scopito v2020 profile and interim templates, **When** this feature is delivered, **Then** they continue to work unchanged and their behaviour on existing fixtures is byte-identical.

---

### User Story 3 - Onboard a new PDF target format (Priority: P3)

An analyst receives the client's mandated target format as a PDF. They run a draft-template command. If the PDF is a fillable form, the tool enumerates its form fields into a proposed field schema. If it is a fixed-layout document, the tool proposes labelled target regions with page coordinates. The analyst validates or corrects the proposal and approves it, registering a versioned TargetTemplate with a required-field schema and validation rules.

**Why this priority**: Target formats arrive as PDFs in practice (Annexure-style packs, client pro formas). This removes the other half of the hand-building cost, but it depends on the draft/approve machinery from stories 1–2 and is only monetised once story 4 can render into it.

**Independent Test**: Run the draft-template command against one fillable-form PDF and one fixed-layout PDF; verify the form yields a proposed field schema and the fixed-layout yields labelled regions with page coordinates; correct, approve, and verify a versioned TargetTemplate is registered with required fields and validation rules.

**Acceptance Scenarios**:

1. **Given** a fillable-form target PDF, **When** the analyst runs the draft-template command, **Then** the tool enumerates the form's fields into a proposed field schema (field names, kinds, and any fixed options) for review.
2. **Given** a fixed-layout (non-form) target PDF, **When** the analyst runs the draft-template command, **Then** the tool proposes labelled target regions with page coordinates for review.
3. **Given** a draft template proposal, **When** the analyst validates/corrects and approves it, **Then** a versioned TargetTemplate is registered with a required-field schema and validation rules, following the same draft → approved lifecycle as source profiles.
4. **Given** a target PDF that is neither a fillable form nor a fixed-layout text document (e.g., scanned image), **When** the draft-template command runs, **Then** it is rejected with a clear explanation rather than producing a misleading proposal.

---

### User Story 4 - Produce filled PDFs in an onboarded target format (Priority: P4)

An analyst who has applied a batch (records already mapped and validated) produces the client deliverable in a PDF target format registered via story 3. Fillable-form targets are filled field-by-field; fixed-layout targets are rendered by overlaying values at the registered coordinates on the original PDF. The produced output must round-trip: values read back from the produced PDF match the applied records.

**Why this priority**: This completes the end-to-end path — without it, an onboarded PDF target is registered but unusable. It depends on story 3's registered templates and the existing apply pipeline.

**Independent Test**: From an applied batch and an approved PDF TargetTemplate, render the output PDF; read the values back out of the produced file and compare them to the batch records.

**Acceptance Scenarios**:

1. **Given** an applied batch and an approved fillable-form TargetTemplate, **When** the output is rendered, **Then** each mapped record value is written into its registered form field, and reading the fields back from the produced PDF returns exactly the applied values (exact round-trip).
2. **Given** an applied batch and an approved fixed-layout TargetTemplate, **When** the output is rendered, **Then** every mapped value appears at its registered page coordinates on the original PDF, verified by a golden-file comparison of extracted text plus coordinates.
2a. **Given** an applied batch whose records carry extracted images and a template with registered image regions, **When** the output is rendered, **Then** each record's image appears in its registered region, scaled to fit without cropping, and its presence and content are verified on read-back.
3. **Given** a record missing a value for a required target field, **When** rendering runs, **Then** the gap is reported as an exception — never silently absorbed or filled with a guess.
4. **Given** the same applied batch, transform version, and template version, **When** rendering is re-run, **Then** the output content is identical (timestamps excepted).

---

### Edge Cases

- **Scanned/image-only PDF submitted for onboarding (source or target)**: detected and rejected with a clear message; the occurrence is logged as a future assumption to resolve (OCR is out of scope).
- **Encrypted, password-protected, or XFA (LiveCycle) target PDF**: rejected with a diagnosis naming the specific condition and its workaround (unlocked copy, or flatten to fixed-layout) — plausible for utility/government paperwork, so the message must be actionable, not generic.
- **Low-confidence proposal elements**: elements below a confidence floor are flagged for mandatory review attention, never silently pre-confirmed.
- **PDF that is both a fillable form and has fixed-layout content**: form fields take precedence for the proposal; the analyst can see and correct the classification before approval.
- **Records spanning page breaks or repeated per-page headers/footers in a source PDF**: the draft recipe must account for page anatomy so repeated furniture is not proposed as record data.
- **A value too long for its registered fixed-layout region**: reported as a validation exception on render, not silently truncated or overflowed.
- **Re-onboarding a shape that already has a registered profile**: produces a new draft proposal that, on approval, becomes a new profile version — never a mutation of the existing one.
- **Abandoned drafts**: a draft left unapproved has no effect on any conversion; it can be discarded or superseded without trace in apply behaviour.
- **Same-profile input that later drifts structurally**: existing structure-drift protection (SafeCard blocking) applies to profiles created via onboarding exactly as to hand-built ones; the block outcome additionally points the analyst at the re-onboarding path (see FR-021) instead of leaving a dead end.
- **Approving a proposal with unresolved (neither confirmed nor corrected) elements**: approval is blocked until every proposed element has been explicitly confirmed, corrected, or removed.
- **Single-exemplar overfit**: a recipe drafted from one exemplar may encode that document's quirks (page count, optional sections); supplying optional extra exemplars cross-checks the proposal, and non-generalising elements are down-scored and flagged rather than silently kept.
- **Record without a photo, or photo without a record**: a missing image for a record with a registered image region is an exception at render time; an orphan image in the source that matches no record is flagged during extraction review, never silently attached to the wrong record.
- **Image aspect ratio vs registered region**: images are scaled to fit within the region preserving aspect ratio — never cropped or stretched; if the result would be illegibly small, that is flagged during template review (region too small), not at batch time.

## Requirements *(mandatory)*

### Functional Requirements

**Source-shape onboarding**

- **FR-001**: The system MUST provide a draft-profile command that, given a structured source PDF with no matching registered profile, analyses the document's structure (repeating structures, tables, header/label blocks, page anatomy) and produces a draft extraction recipe proposing: header fields, record-row locations, and the columns/labels each record carries. The command requires one exemplar PDF and MAY accept additional same-shape exemplars; when extras are supplied they are used to cross-check the proposal, and elements that fail to generalise across exemplars are down-scored and flagged for review.
- **FR-001a**: Draft extraction recipes MUST support per-record image elements: the analysis proposes image regions associated with each record (e.g., defect photos), and approved profiles extract those images as files referenced from the extracted record — matching how the existing hand-built profile handles photos.
- **FR-002**: Every proposed element in a draft extraction recipe MUST carry a per-element confidence score, and confidence MUST reflect structural evidence — field-name overlap alone MUST NOT be presented as confidence.
- **FR-003**: The system MUST provide a review flow in which the analyst can confirm, correct, or remove each proposed element individually, comparing against the actual PDF; approval MUST be blocked while any element remains unresolved. The review flow follows the existing mapping-session pattern (D1): the proposal is an editable persisted document, a generated visual review sheet renders each proposed element against the source PDF, and approval is an explicit separate command.
- **FR-004**: On approval, the system MUST register the validated recipe as a new versioned SourceProfile (starting at v1) in the existing append-only, effective-dated profile registry; from that point extraction for that shape MUST be fully deterministic with no AI involvement.
- **FR-005**: Draft proposals MUST be persisted as reviewable artifacts with a distinct draft status, so a review can be paused and resumed, and so the audit trail shows what was proposed versus what the human changed.

**Target-format onboarding**

- **FR-006**: The system MUST provide a draft-template command that, given a target-format PDF, determines whether it is a fillable form or a fixed-layout document and proposes accordingly.
- **FR-007**: For a fillable-form target PDF, the system MUST enumerate the form's fields into a proposed field schema (field identifiers, kinds, and fixed option sets where present) for analyst review.
- **FR-008**: For a fixed-layout target PDF, the system MUST propose labelled target regions with page coordinates for analyst review. Regions carry a declared kind — text value or image — so a template can register photo placement areas alongside value fields.
- **FR-009**: On approval, the system MUST register a versioned TargetTemplate carrying a required-field schema, validation rules, and a declared output cardinality — per-record (one filled PDF per record) or per-batch (one PDF for the whole batch) — in the existing append-only, effective-dated template registry. Per-record is the primary cardinality delivered first.
- **FR-010**: A target PDF that is neither a fillable form nor a fixed-layout text document (including scanned/image-only PDFs) MUST be rejected with a clear explanation, and the occurrence logged for follow-up. Encrypted, password-protected, and XFA (non-AcroForm) PDFs MUST each be rejected with a diagnosis naming the specific condition and a practical workaround (e.g., obtain an unlocked copy, or flatten via print-to-PDF and onboard as fixed-layout) — never a generic failure and never a best-effort proposal from a partially readable file.

**Rendering into PDF targets**

- **FR-011**: The system MUST render an applied batch into an approved fillable-form TargetTemplate by filling each registered form field with its mapped value.
- **FR-012**: The system MUST render an applied batch into an approved fixed-layout TargetTemplate by overlaying mapped values at the registered page coordinates on the original PDF.
- **FR-012a**: Rendering MUST place record images into registered image regions (fixed-layout targets), scaled to fit the region without cropping; a record image that cannot be placed (missing file, unreadable format) surfaces as an exception, never a silently blank region.
- **FR-013**: Rendered PDF output MUST round-trip: text values read back from the produced PDF MUST match the applied records exactly, and each registered image region MUST contain the placed image (verified by presence and source-content match); a round-trip mismatch is a rendering failure, not a warning.
- **FR-014**: Missing required values, out-of-vocabulary values, and values that do not fit their registered region MUST surface as exceptions in the existing exceptions report — never guessed, truncated, or silently absorbed.
- **FR-015**: Rendering MUST be deterministic: same applied batch + same transform version + same template version produces identical output content (timestamps excepted).

**Draft/approval safety and lifecycle**

- **FR-016**: Draft profiles and draft templates MUST carry a status distinct from approved artifacts, and a batch ApplyRun MUST fail with a clear error — before converting any record — if it references any draft artifact. This failure path MUST be covered by tests.
- **FR-017**: Approval MUST record who approved and when, and human approval is REQUIRED by design for every onboarded artifact — there is no unattended path from proposal to approved (decision D5, to be logged in ASSUMPTIONS.md before implementation).
- **FR-018**: Registered profiles and templates MUST be stored configuration data (schema-validated, human-readable), never generated code; onboarding a new format MUST NOT require changes to pipeline code.
- **FR-019**: Onboarding MUST NOT alter the behaviour of any existing registered profile or template; the existing scopito v2020 profile and interim templates MUST continue to produce identical output on existing fixtures.
- **FR-020**: Document analysis during onboarding MUST transmit no document content to third-party services: deterministic structural heuristics always produce the base proposal, and the existing local AI assistance layer (feature 002) MAY optionally enrich it (field naming, label matching, confidence hints). A `--no-ai` mode MUST yield heuristics-only proposals. AI assistance is confined to the onboarding/drafting session and never runs at apply or render time.
- **FR-021**: When SafeCard blocks a batch input for structural drift, the block verdict and exceptions report MUST recommend the re-onboarding path: running the draft-profile command on the drifted document, seeded with the blocking profile so the analyst reviews the proposal as a delta against the known shape. Block behaviour itself is unchanged, and the seeded proposal follows the full draft → review → approve lifecycle producing a new profile version.

### Key Entities

- **Draft Profile Proposal**: The persisted output of analysing an unrecognised source PDF — proposed header fields, record-row locations, and column/label assignments, each with confidence and a per-element review state (proposed / confirmed / corrected / removed). Status: draft until approved or discarded.
- **Draft Template Proposal**: The persisted output of analysing a target PDF — either a proposed form-field schema or a set of labelled regions with page coordinates, with the same per-element review states and draft status.
- **SourceProfile (extended)**: The existing versioned, append-only registry entry; onboarding adds a creation path (approved-from-proposal) and provenance (which proposal, who approved, when). Existing hand-built profiles are unaffected.
- **TargetTemplate (extended)**: The existing versioned, append-only registry entry; onboarding adds PDF target kinds (fillable-form, fixed-layout) with required-field schema, validation rules, a declared output cardinality (per-record or per-batch), and the same provenance.
- **Approval Record**: Who approved a draft, when, and what the approved content was — the boundary between "AI proposed" and "human validated" in the audit trail.
- **Round-Trip Verification Report**: For each rendered PDF, the read-back comparison of produced values against applied records; part of the batch's audit output.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the held-out structured PDF fixture never used in development (the quarantined Zeitview demo report, see Assumptions), the draft profile proposal extracts at least 80% of records correctly before any human correction.
- **SC-002**: After human validation and approval, 100% of the human-validated subset extracts correctly via the registered profile.
- **SC-003**: An analyst can take an unrecognised structured PDF from first command to approved artifact in under 30 minutes of validation effort, versus hand-building an extraction recipe or template from scratch.
- **SC-004**: A fillable-form PDF target round-trips exactly: every value read back from the produced PDF equals the applied record value, on every batch.
- **SC-005**: A fixed-layout PDF target renders all mapped values at their registered coordinates, verified by a golden-file comparison of extracted text and coordinates.
- **SC-006**: Every attempt to run a batch against a draft artifact fails with a clear error and converts zero records, demonstrated by automated tests.
- **SC-007**: The existing scopito v2020 profile and interim templates produce byte-identical output on existing fixtures before and after this feature ships.
- **SC-008**: 100% of approved artifacts carry an approval record (who, when) and full proposal provenance.

## Out of Scope

- **Scanned/image-only PDFs and OCR**: rejected with a clear message when encountered; each occurrence is logged as a future assumption. No OCR capability is built.
- **Fully-unattended onboarding**: a human approval step is REQUIRED by design (decision D5), not a temporary limitation. No auto-approval path exists at any confidence level.
- **Target formats that are neither fillable-form PDF, fixed-layout PDF, nor the already-supported document/spreadsheet targets.**
- Any classification or defect-severity intelligence (that is v2; this feature only extends v1's onboarding of shapes and formats).

## Assumptions

- **Decision D5** (human approval mandatory for onboarded artifacts, by design) will be logged in ASSUMPTIONS.md before implementation begins, per the project's assumption discipline.
- Approval identity is the operating analyst's configured identity (single-operator tool today); no multi-user authentication or role model is introduced by this feature.
- "Minutes of human validation" is interpreted as: analyst review-and-approve effort under 30 minutes per new format (SC-003) — comfortably inside the existing ≤2-hour one-time-setup budget.
- The held-out acceptance fixture is a Zeitview demo report that Rayno will place in `seed/` — demo data, consistent with the standing rule that no real client reports are used in development or testing. It is quarantined from all development and tuning; SC-001 acceptance is blocked until it is provided.
- Source PDFs in scope have a machine-readable text layer (structured exports, not scans); the two Scopito seed demo exports remain the primary development fixtures, with the held-out Zeitview fixture reserved untouched for acceptance.
- Confidence scores are review aids for the human, not gates: no confidence level bypasses per-element review or approval.
- Record-level correctness for SC-001 means the record's field values are extracted and assigned to the right columns/labels; a record with any misassigned field counts as incorrect.
- Existing structure-drift protection (SafeCard) applies unchanged to onboarded profiles; this feature adds no new drift rules and relaxes none (the block verdict gains a pointer to re-onboarding, FR-021, but block behaviour is untouched).

## Brainstorm Log

### Session 2026-07-12 (superspec brainstorm)

Four edge-case areas explored and resolved:

1. **Exemplar count** — draft-profile takes one exemplar (required) plus optional extras for cross-checking; non-generalising elements are down-scored and flagged (FR-001, single-exemplar-overfit edge case). Guards the ≥80% held-out target against single-document overfit.
2. **Images** — full image support: onboarded recipes extract per-record images as referenced files (FR-001a), fixed-layout templates register image-kind regions (FR-008), rendering places images scaled-to-fit with presence/content round-trip verification (FR-012a, FR-013), plus missing-photo/orphan-image and aspect-ratio edge cases. Initially answered text-only, revised to full support on reflection — defect photos are the evidence that makes converted reports usable.
3. **Drift → re-onboarding** — a SafeCard drift BLOCK now recommends the recovery path: draft-profile seeded with the blocking profile, reviewed as a delta, approved as a new version (FR-021). Block semantics unchanged.
4. **Hostile target PDFs** — encrypted / password-protected / XFA targets are rejected with a per-condition diagnosis and workaround, never a best-effort proposal (FR-010 extended). Anticipates utility/government paperwork.
