# Report-Mapping Utility (`rmu`)

**Map one report, convert hundreds.** `rmu` converts drone-inspection source
reports (Scopito exports today) into a client's mandated target format. The
mapping is made **once** per (source shape, target format) pair — AI-assisted,
with a human approving every decision — stored as a versioned transform, and
then applied **deterministically** to every subsequent report of the same
shape with zero human field decisions.

```
detect(source_doc)            -> SourceProfile (or unknown -> quarantine)
extract(source_doc, profile)  -> NormalizedRecords
map(profile, template)        -> Transform          # human-in-the-loop, ONCE
apply(records, transform)     -> TargetDraft + ExceptionsReport
validate(draft, template)     -> SafeCard verdict (pass / warn / block)
render(draft, template)       -> output files (csv / docx)
audit(run)                    -> exactly-regenerable ApplyRun record
```

Everything left of `apply` is setup and may be expensive (human minutes, AI
calls). Everything from `apply` rightward is runtime: deterministic,
near-zero-cost, and byte-identically re-runnable. That asymmetry is the
product.

## The problem

Drone-inspection operators receive findings from platforms like Scopito, but
must re-deliver the same findings in each client's mandated format. Today that
conversion is redone by hand for every single report. `rmu` does the human
mapping work once and automates the rest — while refusing, by construction, to
guess.

## Guarantees

These are enforced by tests that are never cut (see `tests/invariants/`):

| Guarantee | Meaning |
|---|---|
| **Deterministic apply** | No AI, no network, no clock at apply time — mechanically enforced by an import-graph test. Same inputs + same transform version + same template version → **byte-identical output files** (straight file hash; outputs embed zero generation timestamps). |
| **Never guess** | A value outside an approved value map, a garbled record, or a vocabulary-illegal target becomes a logged **exception with a suggested resolution** — never a silent default. Every run emits an exceptions report, even a clean one. |
| **Drift is blocked, not absorbed** | A document whose structure drifted (missing anchors, or declared totals ≠ extracted records) is **quarantined per document** with no output, while healthy documents in the batch convert normally. |
| **Append-only registries** | SourceProfiles, TargetTemplates, Transforms, ValueMaps and ApplyRuns are versioned and append-only; UPDATE/DELETE raises at the model layer, and migrations are additive by tested convention. |
| **Exact regeneration** | Any past run is reproducible from its audit record — inputs by content fingerprint, recorded prompt answers, and the **exact pinned transform rows** (a newer transform version never leaks into an old run's regeneration). Verified by hash against the recorded manifest. |
| **Honest trust signals** | SafeCard verdicts derive from value-level coverage, human-confirmed tiers, and exception rates only. Field-name overlap is never presented as confidence. |

## Status

**v1 weekend slice** (2026-07-11): one source profile
(`scopito.pdf.powerline.v2020`, built against two real Scopito demo PDFs), two
**INTERIM** target templates, the full pipeline, and the invariant test suite.

⚠️ **The shipped target formats are interim stand-ins.** The real
client-mandated formats (Eskom Annexure H pro forma, SAP defect-record fields)
are not in hand and are **never invented here** — they arrive later as new
`TargetTemplate` versions, as pure data, with no pipeline changes. See
`ASSUMPTIONS.md` (A1–A8) for the working assumptions and `STATUS.md` for
current build state.

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) (Python 3.12 is pinned and managed).

```bash
uv sync                # install everything
uv run rmu db init     # create the schema (Alembic)
uv run rmu seed load   # register profile, both INTERIM templates, defect codes

# 1) One-time mapping session against ONE exemplar (manual mode — no AI needed)
uv run rmu map start \
  --profile scopito.pdf.powerline@v2020 \
  --template interim.defect_csv@1 \
  --exemplar seed/source_samples/Distribution-report.pdf \
  --no-ai
#    edit the emitted draft YAML, create the value maps it pins, then:
uv run rmu valuemap create --name severity_to_priority \
  --file examples/valuemaps/severity_to_priority.yaml
uv run rmu valuemap create --name issue_to_defect_code \
  --file examples/valuemaps/issue_to_defect_code.yaml
uv run rmu map review  --session 1     # static HTML review sheet
uv run rmu map preview --session 1     # exemplar rendered in the target format
uv run rmu map approve --session 1 --by <you>   # stores Transform v1

# 2) Zero-decision batch conversion (repeat --transform to emit both formats)
uv run rmu apply run tests/fixtures/batch_20 \
  --transform "scopito.pdf.powerline@v2020:interim.defect_csv@1" \
  --transform "scopito.pdf.powerline@v2020:interim.annexc_pack@1" \
  --answer contract_number=DEMO-001
# -> store/runs/<id>/: per-report defect CSVs + report packs
#                      + exceptions.csv (always) + safecard.json

# 3) Trust drills
uv run rmu apply regen 1   # byte-exact regeneration, hash-verified
uv run pytest              # 65 tests incl. determinism / append-only /
                           # drift-block / exceptions invariants
```

Drop `--no-ai` (with `ANTHROPIC_API_KEY` set) for AI-proposed field routes and
value conversions — every proposal enters at tier **T2** and cannot survive
approval without an explicit human decision.

## Worked example — run it on the bundled demo data

Everything below is copy-paste runnable from a fresh clone and was verified
verbatim. It uses the committed demo data (two real Scopito demo PDFs in
`seed/source_samples/` + 18 synthetic same-structure reports in
`tests/fixtures/batch_20/`) and ready-made mapping files in `examples/`.

**1. Set up and start a manual mapping session against ONE exemplar:**

```bash
uv sync
uv run rmu db init
uv run rmu seed load
uv run rmu map start \
  --profile scopito.pdf.powerline@v2020 \
  --template interim.defect_csv@1 \
  --exemplar seed/source_samples/Distribution-report.pdf \
  --no-ai
```

```text
session: 1 mode=manual
draft:   .../store/drafts/session_1.transform.yaml
```

**2. Play the analyst.** Normally you would now edit the emitted draft
(skeleton routes, all unmapped) and decide the value conversions yourself. For
the demo, the finished artifacts are provided — two value maps and a completed
draft (open them; they are commented):

```bash
uv run rmu valuemap create --name severity_to_priority \
  --file examples/valuemaps/severity_to_priority.yaml
uv run rmu valuemap create --name issue_to_defect_code \
  --file examples/valuemaps/issue_to_defect_code.yaml
cp examples/transform.defect_csv.yaml store/drafts/session_1.transform.yaml

uv run rmu map review  --session 1   # HTML review sheet (tier-coloured)
uv run rmu map preview --session 1   # the exemplar rendered as a defect CSV
uv run rmu map approve --session 1 --by demo
```

```text
preview: .../session_1.preview.csv  (rows=10, unresolved cells=0)
approved: transform v1 (id=1) by demo; 11 decisions recorded
```

**3. Convert a 20-report batch with zero field decisions.** Assemble the two
real PDFs plus the 18 synthetic reports and run them through the approved
transform (the contract number is the transform's declared per-batch prompt —
supplied once, up front):

```bash
mkdir -p store/demo_batch
cp tests/fixtures/batch_20/*.pdf seed/source_samples/*.pdf store/demo_batch/
uv run rmu apply run store/demo_batch \
  --transform "scopito.pdf.powerline@v2020:interim.defect_csv@1" \
  --answer contract_number=DEMO-001 --label demo
```

```text
run 1: documents=20 converted=20 blocked=0 exceptions=0
outputs: .../store/runs/1
```

**4. Inspect the outputs** — one defect CSV per source report, plus the
always-present exceptions report (header-only on a clean run) and the
SafeCard:

```bash
head -3 store/runs/1/Distribution-report.defects.csv
```

```text
finding_id,asset_name,inspection_date,defect_code,priority,source_severity,contract_number,inspection_method,user_tags,comments,source_page
1703644,Distribution demo - Lineman analysis,2020-12-02,E7,P1,5,DEMO-001,UAV visual,AOI-1-0127 | RGB,burned arrestor lead,2
1703645,Distribution demo - Lineman analysis,2020-12-02,E7,P1,5,DEMO-001,UAV visual,AOI-1-0127 | RGB,burned arrestor lead Past practice has shown that,3
```

**5. Prove the trust claims:**

```bash
uv run rmu apply regen 1
# regenerated run 1: 20 outputs hash-verified against the recorded manifest
```

**6. Optional — watch drift get blocked.** Add the two deliberately drifted
fixtures (one with a renamed annotation-table header, one that declares 10
annotations but contains 7) and re-run:

```bash
cp tests/fixtures/drifted/*.pdf store/demo_batch/
uv run rmu apply run store/demo_batch \
  --transform "scopito.pdf.powerline@v2020:interim.defect_csv@1" \
  --answer contract_number=DEMO-001 --label demo-drift
```

```text
run 2: documents=22 converted=20 blocked=2 exceptions=2
```

Both drifted documents are quarantined with **no output** — one as an
unrecognized shape, one caught by the declared-vs-extracted integrity check —
and listed in `store/runs/2/exceptions.csv` and the SafeCard batch summary,
while the 20 healthy reports convert normally:

```text
document,kind,reason
count_mismatch.pdf,drift_block,declared totals mismatch: document declares 10 annotations...
drifted_header.pdf,unknown_profile,document does not match any known source profile
```

To also produce the docx report pack in the same run, approve a second
transform for `interim.annexc_pack@1` (same session flow) and pass a second
`--transform` — one audit record then covers both outputs per report. To see
what an unmapped value does, delete any entry from
`examples/valuemaps/issue_to_defect_code.yaml` before step 2: the affected
records land in `exceptions.csv` with a suggested resolution instead of being
guessed.

## CLI overview

| Command | Purpose |
|---|---|
| `rmu db init` / `rmu seed load` | Schema + idempotent data seeding |
| `rmu profile\|template\|valuemap list` | Registry inspection |
| `rmu valuemap create --name N --file F` | Insert a NEW version of a named lookup (append-only) |
| `rmu map start\|review\|preview\|approve` | The human-in-the-loop mapping session |
| `rmu apply run <folder> --transform REF... --answer k=v...` | Deterministic batch conversion; never interactive |
| `rmu apply regen <run-id>` | Exact regeneration of a past run, hash-verified |
| `rmu runs list\|show` | Audit-record inspection |

Exit codes: `0` success · `1` validation error (e.g. missing prompt answers,
empty batch) · `2` blocked (every document quarantined) · `3` approval
preconditions unmet.

## How the mapping session works

1. `map start` extracts the exemplar and emits a **draft transform** (YAML,
   schema-validated) plus starter value-map files. In AI mode, proposals carry
   a confidence tier and one-line rationale; unproposed required fields appear
   as unmapped placeholders.
2. The analyst edits the draft: accept/edit/reject each route, fill remaining
   required fields with **constants**, **formulas** (a closed set of pure,
   declarative operations — no code, no clock, no randomness), or
   **per-batch prompts** (answered once at batch launch, recorded, replayed on
   regeneration).
3. `map review` renders a side-by-side HTML sheet; `map preview` renders the
   exemplar into the actual target format.
4. `map approve` refuses while any required field is unrouted, any AI proposal
   is undecided (tier T2), or any value-map pin is unresolved — then stores the
   transform as a new immutable version with full session lineage.

Confidence tiers (per field): `T0` deterministic · `T1` validated (value-map
backed) · `T2` AI-proposed, pending — never in an approved transform · `T3`
unmapped.

## Repository layout

```
src/rmu/
├── cli.py           # Typer CLI (`rmu`)
├── models.py        # 8 SQLAlchemy entities; append-only ★ tables
├── db.py            # engine/session + AppendOnlyViolation enforcement
├── store.py         # content-addressed blob store (store/objects/<sha>)
├── detect/          # profile fingerprint matching (anchors as data)
├── extract/         # per-profile parsers -> NormalizedRecords
├── mapping/         # HIL session, transform schema/loader, AI providers, review sheet
├── apply/           # pure conversion engine + batch orchestration
├── validate/        # SafeCard scoring + template rule enforcement
└── render/          # deterministic CSV/docx rendering + OPC canonicalizer
templates/           # target formats as DATA (both INTERIM)
profiles/            # source-shape fingerprints + extraction anchors as DATA
seed/                # defect-code vocabulary + the two real Scopito demo PDFs
specs/               # spec-kit artifacts: spec, plan, research, contracts, tasks
tests/               # invariants/ golden/ unit/ integration/ fixtures/
store/               # runtime artifacts (gitignored): DB, blobs, run outputs
```

Templates, profiles, value maps and transforms are **data, not code**: adding
a target format or revising a mapping never touches pipeline code. Transform
YAML is validated against a JSON Schema whose formula grammar and pinned
value-map references are closed by construction.

## Development

```bash
uv run pytest                 # full suite (65 tests)
uv run pytest tests/invariants/   # the never-cut guarantees only
uv run ruff check src tests  # lint
```

- **Fixtures**: `tests/fixtures/build_fixtures.py` (seeded, dev-only reportlab)
  generates the committed synthetic same-structure PDFs, a zero-findings
  report, and two deliberately drifted fixtures used by the drift drill.
- **Golden files**: `tests/golden/make_golden.py` regenerates the committed
  expected outputs — run it only when a rendering change is intended and
  review the diff.
- **Conventions**: educated assumptions are numbered in `ASSUMPTIONS.md` and
  cited as `A#`/`D#` at every reliance site in code and commits. New
  assumptions are logged there *before* use. Session state lives in
  `STATUS.md`.

## Data sensitivity

Real client reports must not be sent to any third-party API until a
data-processing agreement exists with that client. The repo builds and tests
exclusively on the bundled public demo PDFs and synthetic fixtures; the AI
provider is used only in mapping sessions, and the fully manual `--no-ai` path
is a first-class, always-working mode — not a fallback.

## Project documents

| Document | What it is |
|---|---|
| `docs/solution_design_mapping_v1.md` | The authoritative build spec (pipeline, HIL session, SafeCard, data model) |
| `ASSUMPTIONS.md` | Numbered working assumptions (A1–A8) + decision log (D1–D4) |
| `STATUS.md` | Terse per-session build state, decisions, and DoD evidence |
| `specs/001-report-mapping-v1/` | Spec-kit artifacts: spec, plan, research, data model, contracts, tasks |
| `docs/eskom_dst34-1441_extraction.md` | Interim defect taxonomy source for the stand-in vocabulary |
| `.specify/memory/constitution.md` | The nine non-negotiable engineering principles this repo is governed by |
