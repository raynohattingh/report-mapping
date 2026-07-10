<!--
Sync Impact Report
==================
Version change: (template, unversioned) → 1.0.0
Rationale: Initial ratification. Nine principles derived verbatim-in-spirit from the
hard rules in CLAUDE.md (repo root) and docs/solution_design_mapping_v1.md, per the
project owner's instruction on 2026-07-10.

Modified principles: n/a (initial adoption — all placeholders filled)
Added sections:
  - Core Principles (I–IX)
  - Scope Boundaries & Data Constraints
  - Development Workflow & Quality Gates
  - Governance
Removed sections: none (template sections 2/3 instantiated as the two sections above)

Templates requiring updates:
  - .specify/templates/plan-template.md ✅ no change needed — Constitution Check gate
    is derived dynamically from this file
  - .specify/templates/spec-template.md ✅ no change needed — no constitution-specific
    sections present
  - .specify/templates/tasks-template.md ✅ no change needed — task categorization is
    generic; principle-driven tasks (determinism/append-only/drift tests) enter via
    plan's Constitution Check
  - .specify/templates/checklist-template.md ✅ no change needed
  - .specify/templates/commands/ — directory absent, nothing to sync

Follow-up TODOs: none — no deferred placeholders.
-->

# Report-Mapping Utility (rmu) Constitution

Governs v1 of the report-mapping utility: converting drone-inspection source reports
(Zeitview/Scopito exports) into a client-mandated target format via versioned,
human-approved transforms — mapped once, applied deterministically thereafter.
On conflict, precedence is: CLAUDE.md hard rules > `docs/solution_design_mapping_v1.md`
> Spec Kit artifacts (spec/plan/tasks). If a Spec Kit artifact drifts from the design
doc, fix the artifact, never the design.

## Core Principles

### I. TBD Discipline — Never Invent Unresolved Interface Content

The real Eskom Annexure H pro forma (TBD-1) and SAP defect-record fields (TBD-2) are
NOT in hand. Only the two INTERIM target templates defined in design §9 may exist —
(a) the Annex-C-style report pack modeled on `docs/eskom_dst34-1441_extraction.md`,
(b) the generic defect CSV using `seed/defect_codes_v1.csv` — and both MUST live
behind the TargetTemplate registry, clearly labeled INTERIM, so the real formats slot
in later as new template versions. Code, fixtures, and docs MUST NOT fabricate Eskom
content beyond what the extraction doc records. If a task appears to require TBD
content, work STOPS and the blocker is flagged in `STATUS.md`.

*Rationale: guessing a client's mandated format produces output that looks finished
but is contractually wrong; interim-behind-registry keeps the build unblocked while a
gap-test FAIL invalidates none of the engine.*

### II. Deterministic Apply (NON-NEGOTIABLE)

`apply` is a pure function: no AI calls, no network access, no nondeterminism of any
kind at apply time, ever. Same inputs + same Transform version + same TargetTemplate
version MUST yield byte-identical output content (timestamps excepted). A value
falling outside a ValueMap at apply time becomes a logged Exception — flagged and
human-resolved — never an on-the-fly guess or silent default. AI exists only in the
mapping session, as persisted proposals a human reviews before approval.

*Rationale: "expensive once, free thereafter" is the product's entire economic claim;
reproducibility is what makes the audit trail and the map-once promise falsifiable.*

### III. Versioned, Append-Only Registries

`SourceProfile`, `TargetTemplate`, `Transform`, and `ValueMap` are versioned,
append-only, and effective-dated. Revisions create new versions; existing rows are
never mutated or deleted. Any past ApplyRun MUST be exactly regenerable from its
recorded (input hashes, transform version, template version). Destructive migrations
on these tables are prohibited.

*Rationale: regenerability of historical output is an audit requirement and the
foundation of client trust in converted deliverables.*

### IV. Templates and Transforms Are Data, Not Code

Target formats are template files plus schemas; mappings are schema-validated YAML.
Adding a target format or revising a mapping MUST NOT touch pipeline code. Transform
YAML is validated against its JSON Schema before acceptance. Seed vocabularies (e.g.
`seed/defect_codes_v1.csv`) are loaded as data, never hardcoded.

*Rationale: swappable-as-data targets are what let the real Annexure H and SAP formats
arrive without a rewrite, and what makes the product survive a change of institution.*

### V. No False Confidence — SafeCard Honesty

Field-name overlap is NEVER presented or scored as a trust signal. SafeCard reports
only value-level coverage and human-confirmed confidence tiers (T0 deterministic /
T1 validated / T2 proposed / T3 unmapped, per design §7). T2 proposals are never
allowed in an approved Transform. Structural drift suspicion produces a BLOCK verdict
routed to HIL — never a silent best-effort apply. Every ApplyRun emits an exceptions
report, even on a pass verdict.

*Rationale: semantically-wrong-but-structurally-valid output is the product's worst
failure mode precisely because it looks finished.*

### VI. Decoupled Pipeline Stages

The pipeline is Detect → Extract → Map → Apply → Validate → Render → Audit. Each
stage consumes and produces defined artifacts; no stage reaches around another or
inspects another's internals. Per-profile parsers are the only profile-specific code;
everything downstream of Extract is data-driven. A future v2 engine's sole contract
with this tool is "emit NormalizedRecords for some profile."

*Rationale: stage isolation bounds the blast radius of source-format drift and keeps
the v1/v2 boundary clean.*

### VII. Data Sensitivity & the `--no-ai` Guarantee

Real client reports MUST NOT be sent to any third-party API until data-processing
consent exists with that client. Build and test exclusively on the seed demo PDFs
(`seed/source_samples/`) and synthetic fixtures. A `--no-ai` mapping mode (pure-manual
HIL session) MUST always be fully functional, so consent friction can never block
delivery. AI calls, when consented, occur only in mapping sessions on exemplar
documents — never on whole batches, never at apply time (Principle II).

*Rationale: client reports are IAS's — ultimately Eskom's — confidential data; the
manual path is also the D3 degradation floor, so it can never rot.*

### VIII. Test-First on the Invariants (NON-NEGOTIABLE)

The product's core claims MUST have failing tests before feature code layers on:
apply determinism (byte-identical re-runs), append-only enforcement on the four
registry tables, drift-block (a deliberately structure-drifted input is BLOCKED, not
mis-mapped), and exceptions reporting (every batch emits one). Golden-file tests
guard rendering. Under schedule pressure, cut order follows D3 in `ASSUMPTIONS.md`:
these invariants and their tests are NEVER cut.

*Rationale: the invariants ARE the product; untested claims are marketing, not
engineering.*

### IX. Assumption Traceability

Every reliance on an educated assumption cites its ID (`A1`–`A8`) from
`ASSUMPTIONS.md` in code comments and commit messages; decisions are cited as
`D1`–`D4`. New assumptions are logged in `ASSUMPTIONS.md` BEFORE any code relies on
them — never silently adopted. When an assumption clears, `ASSUMPTIONS.md` is updated
and the repo is grepped for its ID to revisit dependent code.

*Rationale: the build deliberately runs ahead of unresolved facts; traceability is
what makes that safe to unwind.*

## Scope Boundaries & Data Constraints

- **In scope (v1):** document-to-document conversion only — bounded, enumerable
  source profiles (Zeitview/Scopito exports), stored transform library, HIL mapping
  session (Option A per D1: CLI + YAML + generated HTML review sheet), batch apply,
  SafeCard validation, audit. Single-operator, local/single-VM deployment (A5).
- **Out of scope (v1) — locked rulings, do not re-litigate in the repo:** SOE or
  government portal integration; a generic "any doc → any doc" mapper; image
  classification, anomaly ML, or annotation UI (all v2 — separate design, held kit,
  none of it built here); flight planning or hosting platforms; multi-tenant SaaS
  infrastructure.
- **No universal schema:** NormalizedRecords stays a thin per-profile extraction
  product with a small shared core (design §5). A universal inspection ontology is
  prohibited until a third source family forces generalization.
- **Stack (fixed for v1):** Python 3.12, uv, pytest, ruff, SQLAlchemy + Alembic on
  SQLite (Postgres-ready by config), Typer CLI, docxtpl + openpyxl, pdfplumber,
  anthropic SDK (mapping session only), PyYAML + jsonschema. Repo layout per
  design §10. Type hints everywhere; small modules; no abstraction beyond the stage
  interfaces.
- **Resources:** personal hardware, personal accounts, personal time only. No
  employer resources, ever.

## Development Workflow & Quality Gates

- **Spec Kit flow:** features proceed through `/speckit.specify` → plan → tasks →
  implement on feature branches. Every plan's Constitution Check gates against the
  nine principles above; violations require an explicit Complexity Tracking entry or
  the plan is reworked.
- **Session hygiene:** `STATUS.md` is updated at the end of every working session —
  done, decisions, next, open questions — current and terse. Proposed deviations from
  the design doc are recorded there, never silently applied.
- **TBD resolution protocol:** when a spec file arrives in `docs/` as
  `spec_update_*.md`, read it, propose the delta in `STATUS.md`, then implement as
  template/data changes first (Principle IV).
- **Definition of done (Gate-2 demo):** from ONE exemplar a human-approved Transform
  is built (≤2h human setup); ≥20 same-profile reports convert with zero human field
  decisions; re-runs are byte-identical; a deliberately drifted input is BLOCKED by
  SafeCard; every batch emits an exceptions report; demo uses only demo/synthetic
  data. Milestones M1–M5 and full acceptance criteria: design doc §11.

## Governance

This constitution operationalizes the hard rules in CLAUDE.md; those rules and the
design doc remain the upstream sources of truth (precedence order in the preamble).
It supersedes all other repo practices and Spec Kit artifacts.

- **Amendments:** proposed as a documented delta (in `STATUS.md` or a PR touching
  this file), approved by the project owner (Rayno), and applied with a version bump
  and Sync Impact Report. Amendments that change CLAUDE.md's hard rules must change
  CLAUDE.md first; this file follows.
- **Versioning:** semantic. MAJOR = principle removal or incompatible redefinition;
  MINOR = new principle or materially expanded guidance; PATCH = clarification or
  wording. Every amendment updates the version line and Last Amended date.
- **Compliance review:** every `/speckit.plan` Constitution Check evaluates the
  gates; every PR/commit relying on an assumption cites its `A#`/`D#` (Principle IX);
  invariant tests (Principle VIII) MUST pass before any milestone is declared done.
  Complexity beyond the stage interfaces must be justified or removed.

**Version**: 1.0.0 | **Ratified**: 2026-07-10 | **Last Amended**: 2026-07-10
