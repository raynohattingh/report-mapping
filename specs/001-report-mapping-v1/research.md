# Phase 0 Research — Report-Mapping Utility v1 (Weekend Slice)

All Technical Context items were pinned by the user input, `docs/solution_design_mapping_v1.md`,
`ASSUMPTIONS.md`, and the 2026-07-10 clarify/brainstorm sessions — no NEEDS CLARIFICATION
markers remained. Research below resolves the *implementation-level* unknowns those
decisions imply.

## R1. Byte-identical DOCX/XLSX output (FR-011, SC-004)

- **Decision**: Render with docxtpl/openpyxl, then pass every rendered file through a
  canonicalization step before it is written to the outputs manifest: rewrite the ZIP
  container with (a) fixed entry order (sorted), (b) fixed entry datetimes (1980-01-01,
  the ZIP epoch), (c) fixed compression level, and (d) `docProps/core.xml`
  created/modified pinned to a fixed value; strip `lastModifiedBy`. CSV/HTML outputs are
  written with `\n` newlines and UTF-8, no BOM.
- **Rationale**: `.docx`/`.xlsx` are ZIP containers; python-docx and openpyxl stamp
  current datetimes into both ZIP entries and OPC core properties, which would break the
  straight-file-hash determinism test the spec demands (brainstorm decision 5). A single
  canonicalizer in `render/` keeps the rule in one place for every output format.
- **Alternatives considered**: masked/fuzzy comparison in tests (rejected by spec —
  "nowhere for nondeterminism to hide"); patching library internals (fragile across
  versions).

## R2. Append-only enforcement at the model layer (Constitution III)

- **Decision**: SQLAlchemy event listeners (`before_update`, `before_delete`) on
  SourceProfile, TargetTemplate, Transform, ValueMap raise `AppendOnlyViolation`;
  the only mutable columns are explicitly whitelisted status flags if the design needs
  them (none do this slice). Alembic migrations for these tables are additive-only by
  convention, checked by a test that walks migration operations.
- **Rationale**: model-layer enforcement is portable across SQLite/Postgres (user
  requirement) and testable without DB-specific triggers.
- **Alternatives considered**: DB triggers (duplicated per-dialect logic); "just don't
  update" convention (untestable, violates Constitution VIII).

## R3. Content-addressed blob store

- **Decision**: `store/objects/<sha256[:2]>/<sha256>` for source documents, rendered
  outputs, review sheets; DB rows hold the hash + metadata only. Store writes are
  write-once (existing hash short-circuits). `store/` is gitignored.
- **Rationale**: regeneration (FR-017/18) needs inputs retrievable by fingerprint;
  content addressing makes duplicate detection (edge case) and byte-identity checks
  trivial.
- **Alternatives considered**: DB blobs (bloats SQLite, complicates Postgres move);
  plain filenames (collision- and rename-fragile).

## R4. Scopito PDF extraction approach (A1, A3)

- **Decision**: pdfplumber, anchor-based: locate the header block by page-1 labels
  (inspection name/date/type/company/counts), the severity overview by its
  "Severity"/POI labels, and the annotation table by its header row
  `Id, Severity, User tags, Issues, Comments, Page`; parse rows with per-profile
  table settings. The header's declared annotation/image counts feed the FR-016
  integrity cross-check (declared totals vs extracted rows). Anchors and settings live
  in `profiles/scopito.pdf.powerline.v2020.yaml` as data.
- **Rationale**: anchors-as-data is what makes drift detectable (missing anchor →
  BLOCK) and a future profile version a data change, per design §4/§9.
- **Alternatives considered**: camelot/tabula (heavier deps; design says only if
  pdfplumber is defeated — it isn't on the two demo PDFs).

## R5. Transform YAML format + closed formula set (FR-007, Constitution IV)

- **Decision**: One YAML document per transform version, validated by a versioned JSON
  Schema (`src/rmu/mapping/schemas/transform-v1.json`). Formulas are declared as data:
  `{fn: concat|substring|regex_extract|date_format|number_format|arith, args: [...]}`,
  where args reference extracted fields, literals, or prompt keys. Value-map references
  are `{name, version}` — version REQUIRED (spec brainstorm decision 1). Per-batch
  prompts declared as `{key, label, required}`.
- **Rationale**: schema-validated closed set implements the brainstorm formula ruling;
  pinned value-map refs make the transform version transitively fix all lookups.
- **Alternatives considered**: sandboxed expression language (rejected in brainstorm —
  new invariant to defend).

## R6. AI provider isolation (A6, Constitution VII)

- **Decision**: `mapping/providers.py` defines a `ProposalProvider` protocol
  (`propose(exemplar_records, template_schema, value_vocabs) -> list[Proposal]`).
  Implementations: `AnthropicProvider` (anthropic SDK, model `claude-fable-5`,
  constructed ONLY inside the mapping session when `--no-ai` is absent and an API key
  exists) and `NullProvider` (returns no proposals; the manual path). Tests use a
  `StubProvider` with canned proposals — no network in any test.
- **Rationale**: keeps AI at the edge, makes `--no-ai` a first-class path (D3 floor),
  and keeps apply free of any provider import.
- **Alternatives considered**: module-level client (leaks AI into import graph);
  recording real API responses (network in CI, consent optics).

## R7. Synthetic same-structure and drifted fixtures (SC-002, SC-003)

- **Decision**: a dev-only fixture builder (`tests/fixtures/build_fixtures.py`) using
  **reportlab** (dev dependency only, never imported by `src/rmu`) generates ≥18
  synthetic PDFs mimicking the 2020 Scopito layout (header block → severity overview →
  annotation table), with varied names/dates/severities/labels drawn from a fixed seed
  so fixture generation is itself deterministic. The drifted fixture renames the
  annotation-table header (`Id` → `Ref`) and drops the severity overview — anchors
  missing → BLOCK. A second integrity fixture declares 10 annotations but contains 7
  rows — count mismatch → BLOCK. Generated PDFs are committed so tests never regenerate.
- **Rationale**: the DoD counts *reports* (documents) and the drift drill must enter
  through Detect/Extract; pre-extracted record fixtures would bypass the very stages
  under test.
- **Alternatives considered**: hand-mangled copies of the real PDFs (opaque, unrepeatable);
  JSON record fixtures (don't exercise Detect/Extract).

## R8. Per-batch prompt answers at the CLI (FR-011, FR-017)

- **Decision**: `rmu apply run <folder> --transform <id@ver> --answer key=value ...`;
  the command fails fast listing missing prompt keys; answers are stored on the
  ApplyRun and replayed by `rmu apply regen <run-id>`.
- **Rationale**: implements the brainstorm ruling (upfront inputs, recorded, never
  interactive).

## R9. Storage/config

- **Decision**: SQLAlchemy 2.x typed ORM + Alembic; engine URL from `RMU_DB_URL`
  (default `sqlite:///store/rmu.db`); SQLite `foreign_keys=ON` pragma. All
  registry loads (defect codes, profiles, templates) are idempotent seed commands.
- **Rationale**: design §8 ruling (D4), Postgres-ready by config.

## R10. SafeCard scoring shape (FR-015)

- **Decision**: verdict computed per document — inputs: profile match + integrity
  signals (R4), % of required target fields at T0/T1 (from the transform), % of this
  document's values covered by pinned value maps, exception count. Batch summary
  aggregates per-document verdicts (counts + worst-case prominence ordering). Blocked
  documents are quarantined; healthy ones proceed (clarify decision 1).
- **Rationale**: spec FR-015/FR-016 as clarified; tiers per design §7 (T0–T3), T2
  never in an approved transform.
