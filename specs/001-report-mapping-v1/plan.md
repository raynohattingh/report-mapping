# Implementation Plan: Report-Mapping Utility v1 — Map Once, Convert Many (Weekend Slice)

**Branch**: `001-report-mapping-v1` | **Date**: 2026-07-10 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/001-report-mapping-v1/spec.md`

## Deviations from `docs/solution_design_mapping_v1.md`

The design doc is authoritative; this plan conforms. Three *refinements* (decided in
the 2026-07-10 clarify/brainstorm sessions) go beyond its letter and will be proposed
as deltas in `STATUS.md` per CLAUDE.md's deviation rule:

1. **SafeCard verdict granularity** — design §7 words verdicts at batch level; the
   spec refines to per-document verdicts with a batch summary (drifted/unknown docs
   quarantined; healthy docs convert). Strictly stronger than §7's intent.
2. **Value-map version pinning** — design §8 versions ValueMaps but doesn't state how
   transforms reference them; the spec requires exact-version pins inside the
   transform YAML (regeneration correctness).
3. **Timestamp discipline** — design §1 says "byte-identical (timestamps excepted)";
   the spec hardens to *no embedded timestamps at all* (canonicalized outputs, straight
   file-hash tests). Strictly stronger.

No other deviations. Everything else below is design §§4–11 made concrete.

## Summary

Build the weekend slice: one source profile (`scopito.pdf.powerline.v2020`, from the
two real demo PDFs), two INTERIM target templates, a human-in-the-loop mapping session
(manual `--no-ai` core path + AI proposals + HTML review sheet), deterministic batch
apply with per-document SafeCard/quarantine, canonicalized rendering, append-only
audit with exact regeneration — proven by invariant tests (determinism, append-only,
drift-block, exceptions-report) that are never cut (D3).

## Technical Context

**Language/Version**: Python 3.12, managed by uv
**Primary Dependencies**: Typer (CLI `rmu`), SQLAlchemy 2.x + Alembic, pdfplumber,
PyYAML + jsonschema, docxtpl + openpyxl, Jinja2 (HTML review sheet), anthropic SDK
(behind `ProposalProvider`, mapping session only, research R6); dev-only: pytest,
ruff, reportlab (fixture builder only, R7)
**Storage**: SQLite via SQLAlchemy (`RMU_DB_URL` config → Postgres-ready, D4);
content-addressed blob store `store/objects/` (R3), gitignored
**Testing**: pytest — golden-file tests (rendering), determinism/property tests
(apply), append-only enforcement tests, drift-block tests, exceptions-report tests
**Target Platform**: local single machine (macOS/Linux), single operator (A5)
**Project Type**: CLI tool + library (`src/` layout)
**Performance Goals**: batch of 20+ PDF reports converts in minutes on a laptop; no
other targets this slice (A5)
**Constraints**: apply path deterministic — no AI/network/nondeterminism imports
(Constitution II); no real client data to third-party APIs (Constitution VII);
outputs embed zero generation timestamps (R1)

## Constitution Check

*GATE: evaluated pre-research and re-evaluated post-design — both pass.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. TBD discipline | PASS | Only the two INTERIM templates (design §9, A2), `interim=true` flagged, behind the TargetTemplate registry; zero fabricated Eskom content (SC-008). |
| II. Deterministic apply | PASS | Apply is a pure function; provider interface unreachable from apply path; canonicalized outputs (R1); prompts as recorded upfront inputs (R8); closed formula set (R5). |
| III. Append-only registries | PASS | Model-layer enforcement + additive-migration test (R2); ApplyRun regeneration hash-verified (contracts/cli-commands.md). |
| IV. Data, not code | PASS | Transform YAML + JSON Schema (R5); templates/profiles/seed loaded as data; formulas declared as data. |
| V. SafeCard honesty | PASS | Verdict inputs: value coverage, tiers, exception rate only (R10); field-name overlap appears nowhere in scoring; T2 blocks approval. |
| VI. Decoupled stages | PASS | Package-per-stage layout; NormalizedRecords contract is the only Extract→downstream interface (contracts/normalized-records.md). |
| VII. Data sensitivity + `--no-ai` | PASS | Demo/synthetic fixtures only; `NullProvider` makes manual mode first-class and built FIRST in P3 (D3). |
| VIII. Test-first invariants | PASS | P1/P4 write failing invariant tests before features; [TDD] markers below; D3 forbids cutting them. |
| IX. Assumption traceability | PASS | A1/A3 (extraction), A2 (templates), A5–A8 cited in code comments and commits at each use site. |

**Complexity Tracking**: no violations — section omitted.

## Project Structure

### Documentation (this feature)

```text
specs/001-report-mapping-v1/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/{cli-commands,transform-yaml,normalized-records}.md
├── checklists/requirements.md
└── tasks.md                      # /speckit-tasks output (next step)
```

### Source Code (repository root)

```text
pyproject.toml                    # uv-managed; rmu console script
alembic/                          # migrations (additive-only on ★ tables)
src/rmu/
├── cli.py                        # Typer app: db/seed/profile/template/map/apply/runs
├── config.py                     # RMU_DB_URL, store path
├── db.py                         # engine/session, append-only listeners (R2)
├── models.py                     # 8 entities per data-model.md
├── store.py                      # content-addressed blob store (R3)
├── detect/                       # fingerprint match → profile | unknown
├── extract/                      # scopito_pdf_powerline.py (pdfplumber, anchors from profiles/*.yaml)
├── mapping/                      # session, draft YAML io, providers.py (R6),
│   ├── schemas/transform-v1.json #   formula grammar + pinned valuemap refs (R5)
│   └── review_sheet.py           # Jinja2 static HTML
├── apply/                        # pure function: (records, transform, answers) → draft + exceptions
├── validate/                     # safecard.py: tiers, coverage, per-doc verdict (R10)
└── render/                       # docxtpl/openpyxl/csv + canonicalize.py (R1)
templates/                        # interim.annexc_pack/, interim.defect_csv/  (data)
profiles/                         # scopito.pdf.powerline.v2020.yaml           (data)
seed/                             # defect_codes_v1.csv, source_samples/ (existing)
store/                            # gitignored: objects/, runs/, rmu.db
tests/
├── fixtures/                     # build_fixtures.py (reportlab, dev-only) + committed PDFs
│   ├── batch_20/                 # 2 real + ≥18 synthetic same-structure
│   └── drifted/                  # renamed-header + count-mismatch fixtures
├── invariants/                   # determinism, append_only, drift_block, exceptions_report  [never cut]
├── golden/                       # rendering golden files
└── unit/…                        # per-stage tests
```

**Structure Decision**: `src/` layout with one package per pipeline stage
(Constitution VI); everything swappable ships as data under `templates/`,
`profiles/`, `seed/`.

## Implementation Phases (the weekend)

### P1 — Scaffold + registries + transform schema (Sat AM)

pyproject/uv scaffold, ruff, pytest wiring; models per data-model.md; append-only
listeners + **failing invariant tests first** (append-only, additive migrations);
Alembic baseline; content store; transform-v1 JSON Schema + validator; seed loaders
(defect codes as data, interim template registration, profile registration);
`rmu db init`, `rmu seed load`, list commands. **Gate**: invariant tests green;
`rmu seed load` idempotent.

### P2 — Extraction + detection + fixtures (Sat midday)

Detect fingerprinting from profile YAML anchors (unknown → quarantine path);
pdfplumber parser for the two real PDFs → NormalizedRecords per contract; integrity
signals (anchors, declared-vs-extracted cross-check); fixture builder + committed
batch_20 and drifted fixtures (R7). **Gate**: both real PDFs extract with
`declared == extracted`; drifted fixtures fail integrity.

### P3 — Mapping session (Sat PM; internal cut order per D3)

1. **Manual `--no-ai` path FIRST**: `map start` skeleton draft + unmapped-required
   list; YAML edit loop; schema validation; `map preview`; `map approve` with FR-007
   preconditions; Transform + ValueMap persistence with pinned versions; session
   lineage (FR-021).
2. **AI proposals second**: `ProposalProvider` protocol, `AnthropicProvider`
   (demo data only, A6), StubProvider for tests; proposals persisted with
   tier+rationale, T2 until human decision.
3. **HTML review sheet third**: Jinja2 side-by-side sheet (exemplar values, proposal,
   rationale, decision state).

**Gate**: approved Transform v1 exists for `interim.defect_csv` from the
Distribution exemplar via the manual path alone.

### P4 — Apply + SafeCard + render + audit + drift drill (Sun)

Pure-function apply (OOV → Exception, never guess); per-document SafeCard verdicts +
batch summary; quarantine flow; renderers + ZIP/OPC canonicalizer (R1) with golden
tests; exceptions report always; ApplyRun audit (completion-only write) +
`apply regen` with hash verification; **determinism + drift-block + regeneration +
exceptions invariant tests**; end-to-end DoD run: batch_20 with zero field decisions,
drifted fixtures blocked, byte-identical re-run. Second interim template
(`interim.annexc_pack`, docxtpl) lands here; it is D3 cut #3 if Sunday slips.
**Gate**: SC-001…SC-008 all demonstrably met; STATUS.md updated with the three
design-refinement deltas.

## Execution Strategy

### TDD Requirements

- [ ] `apply/` + `render/canonicalize` [TDD]: determinism is the product's core claim —
  byte-identity tests written before the code they constrain (Constitution VIII).
- [ ] `db.py` append-only listeners [TDD]: mutation attempts must fail before any
  feature relies on registry immutability.
- [ ] `detect/` + integrity signals [TDD]: drift-block tests (renamed header, count
  mismatch) written against fixtures before parser hardening.
- [ ] Exceptions reporting [TDD]: "report always exists, OOV never guessed" tests
  precede apply features.

### Parallel Execution Opportunities

- [ ] P2 fixture builder ∥ P2 extractor (share only the NormalizedRecords contract).
- [ ] P3 review sheet ∥ P3 AI provider (both consume the draft-session model).
- [ ] P4 `interim.annexc_pack` docx rendering ∥ P4 SafeCard scoring (no shared files).
- [ ] Golden-file test authoring ∥ renderer implementation (contract-first).

### Human Checkpoints

1. End of P1 — registries + append-only invariants green before anything builds on them.
2. End of P3 — human runs the manual mapping session on the exemplar and approves
   Transform v1 (this is itself US1 acceptance).
3. End of P4 — full DoD run + drift drill reviewed against SC-001…SC-008; STATUS.md
   session entry written (Constitution: workflow rule).

### Review Gates

- [ ] Transform YAML schema (contracts/transform-yaml.md): review before the mapping
  session consumes it — every later stage trusts it.
- [ ] Append-only enforcement + Alembic baseline: review before P2 (data-model change
  gate).
- [ ] `apply/` pure-function boundary: review that no provider/network import is
  reachable before P4 integration.
