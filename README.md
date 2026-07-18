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
render(draft, template)       -> output files (csv / docx / filled PDF)
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

**Local AI assistance** (feature `002-local-ai-assist`, 2026-07-12): the mapping
session can now propose field routes and value maps **entirely on-device** — no
data leaves the machine — with a consent-gated opt-in for an external API. See
[Local AI assistance](#local-ai-assistance) below.

**Assisted format onboarding** (feature `003-pdf-format-onboarding`, 2026-07-13):
a source PDF the tool has never seen, or a client's target format supplied as a
PDF, is onboarded in minutes: the tool analyses the document and proposes a
draft extraction recipe / template schema, a human validates every element, and
a machine-checked approval gate registers it as a versioned artifact. Drafts can
never convert data. See
[Onboarding a new format](#onboarding-a-new-format-source-or-target) below.

**Mapping Studio** (feature `004-mapping-studio`, 2026-07-15): a strictly-local
web app that becomes the primary human-in-the-loop surface — see the actual
documents and connect them visually instead of hand-editing draft YAML. The
studio owns **zero business logic**: every action runs the same code path as the
CLI and produces identical stored artifacts, so the two surfaces are
interchangeable mid-draft. It is a **deletable optional package** — the CLI stays
canonical for batch and the full product works without it. See
[Mapping Studio](#mapping-studio) below.

**Matrix-aware target onboarding** (feature `005-matrix-target-onboarding`,
2026-07-16): grid-form targets — inspection checklists whose rows are
**criteria** (numbered, e.g. `4.2 Corrosion`) and whose columns are **towers /
assets** — now onboard as a real two-axis matrix instead of hundreds of flat
regions with positional names. The analyst reviews ~25 axis entries, not ~373
cells; every cell derives its identity (`corrosion__t2`) from the two axes. An
optional AI **interpret** stage (local vision model by default) reads the page
and proposes axis structure/labels **by grid index only** — it can never emit a
coordinate, and every suggestion is human-confirmed. See
[Matrix targets](#matrix-targets-grid-checklists) below.

⚠️ **The shipped target formats are interim stand-ins.** The real
client-mandated formats (Eskom Annexure H pro forma, SAP defect-record fields)
are not in hand and are **never invented here** — they arrive later as new
`TargetTemplate` versions, as pure data, with no pipeline changes. See
`ASSUMPTIONS.md` (A1–A14, D1–D12) for the working assumptions and `STATUS.md` for
current build state.

## Mapping Studio

A local, single-user web front-end for the mapping and onboarding sessions —
the visual alternative to hand-editing draft YAML next to a static review sheet.

```bash
uv sync --group studio          # the studio's deps are an OPTIONAL group
uv run rmu studio               # binds 127.0.0.1 only; prints/opens a
                                # per-launch secret URL (never persisted)
```

- **Dashboard** of every registry, session, proposal and apply-run (with its
  SafeCard verdicts, coverage and exceptions), plus local-AI health and
  per-client external-consent management.
- **Visual mapping canvas** — exemplar and target rendered as their real pages,
  extraction elements highlighted, links drawn between panes; accept/reject AI
  proposals, draw manual links, edit value maps at the link with observed values
  in view, preview in the target's actual format, and approve — a whole session
  without touching YAML.
- **Visual onboarding review** — proposals reviewed on the rendered PDF with
  keyboard triage (confirm/rename/remove + auto-advance), drag/resize and draw
  missed regions; approval runs the same verify-on-approve proof.
- **Axis-first matrix review** — a matrix proposal (grid checklist) is reviewed
  as its two axes: Criteria and Towers panels with AI suggestions shown pending
  (accept/reject/rename per entry, keyboard triage with auto-advance), row/column
  band highlights on the page, cells derived — ~25 decisions instead of hundreds.

Everything the studio does is one of the existing lifecycle transitions through
the same functions the CLI calls, so a draft started in one surface is finishable
in the other. The studio binds loopback-only, guards every request with a
per-launch secret + Host/Origin checks, and persists no document data in the
browser. Deleting the `rmu.studio` package (or omitting the `studio` group)
leaves every CLI capability and the full test suite intact.

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) (Python 3.12 is pinned and managed).

```bash
uv sync                # install everything
uv run rmu db init     # create the schema (Alembic)
uv run rmu seed load   # register profile, both INTERIM templates, defect codes
uv run rmu ai setup    # one-time local-AI model setup steps (then `rmu ai doctor` to verify)

# 1) One-time mapping session against ONE exemplar.
#    `local` is the default assist mode: on-device AI proposes ranked field
#    routes + value maps, nothing leaves the machine. (Add `--no-ai` for a fully
#    manual session — always available, no models needed.)
uv run rmu map start \
  --profile scopito.pdf.powerline@v2020 \
  --template interim.defect_csv@1 \
  --exemplar seed/source_samples/Distribution-report.pdf
#    review/edit the emitted draft YAML, create the value maps it pins, then:
uv run rmu valuemap create --name severity_to_priority \
  --file examples/valuemaps/severity_to_priority.yaml
uv run rmu valuemap create --name issue_to_defect_code \
  --file examples/valuemaps/issue_to_defect_code.yaml
uv run rmu map review  --session 1     # static HTML review sheet (AI rows + drop counts)
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
uv run pytest              # 400+ tests incl. determinism / append-only /
                           # drift-block / exceptions / offline-AI / draft-block
                           # / render round-trip invariants
```

Every AI proposal enters at tier **T2** and cannot survive approval without an
explicit human decision — identical to the manual flow, just pre-filled. If the
local models aren't installed, `local` mode degrades cleanly to the manual
experience (embeddings-only still ranks candidates). See
[Local AI assistance](#local-ai-assistance) for the modes, tiers, and the
consent gate on the external-API option.

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
  --no-ai   # demo-only: keeps this walkthrough reproducible on a clone with
            # no models installed. Day to day, omit it - local AI is the default.
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

**6. Add the document deliverable — a docx report pack per source PDF.** The
CSV is the machine-readable target; the report pack is the human-readable one
(an Annex-C-style inspection document rendered per report). Approve a second
transform for it — same session flow, reusing the same two value maps — then
run BOTH targets in one batch under a single audit record:

```bash
uv run rmu map start \
  --profile scopito.pdf.powerline@v2020 \
  --template interim.annexc_pack@1 \
  --exemplar seed/source_samples/Distribution-report.pdf \
  --no-ai                                     # demo-only (see step 1) -> session: 2
cp examples/transform.annexc_pack.yaml store/drafts/session_2.transform.yaml
uv run rmu map preview --session 2            # writes session_2.preview.docx
uv run rmu map approve --session 2 --by demo

uv run rmu apply run store/demo_batch \
  --transform "scopito.pdf.powerline@v2020:interim.defect_csv@1" \
  --transform "scopito.pdf.powerline@v2020:interim.annexc_pack@1" \
  --answer contract_number=DEMO-001 --label demo-both
```

```text
run 2: documents=20 converted=20 blocked=0 exceptions=0
```

`store/runs/2/` now holds **40 outputs**: per source PDF one
`<report>.pack.docx` (open it — inspection details plus a findings table with
the converted defect codes and priorities) and one `<report>.defects.csv`.
The packs are OPC-canonicalized, so `rmu apply regen 2` hash-verifies all 40
byte-for-byte. Need PDF delivery? Word/LibreOffice export the pack as-is —
and because target formats are data, a real client's pro forma later replaces
this interim pack as just a new template version.

**7. Optional — watch drift get blocked.** Add the two deliberately drifted
fixtures (one with a renamed annotation-table header, one that declares 10
annotations but contains 7) and re-run the same two-target command:

```bash
cp tests/fixtures/drifted/*.pdf store/demo_batch/
uv run rmu apply run store/demo_batch \
  --transform "scopito.pdf.powerline@v2020:interim.defect_csv@1" \
  --transform "scopito.pdf.powerline@v2020:interim.annexc_pack@1" \
  --answer contract_number=DEMO-001 --label demo-drift
```

```text
run 3: documents=22 converted=20 blocked=2 exceptions=2
```

Both drifted documents are quarantined with **no output of either kind** — one
as an unrecognized shape, one caught by the declared-vs-extracted integrity
check — and listed in `store/runs/3/exceptions.csv` and the SafeCard batch
summary, while the 20 healthy reports convert normally:

```text
document,kind,reason
count_mismatch.pdf,drift_block,declared totals mismatch: document declares 10 annotations...
drifted_header.pdf,unknown_profile,document does not match any known source profile
```

To see what an unmapped value does, delete any entry from
`examples/valuemaps/issue_to_defect_code.yaml` before step 2: the affected
records land in `exceptions.csv` with a suggested resolution instead of being
guessed.

## Onboarding a new format (source or target)

Feature 003 removes the last hand-building step: when a **source PDF doesn't
match any registered profile**, or a client hands you their **target format as
a PDF** (fillable form or fixed layout), you onboard it instead of writing
code. The default mode of operation is **AI-assisted with the local model** —
heuristics propose the structure deterministically and the on-device LLM adds
naming hints; nothing leaves the machine. Reach for `--no-ai` only when the
local AI isn't working on your machine (`rmu ai doctor` will tell you) — it is
a fallback flag, not the normal flow.

**A. New source shape → registered SourceProfile:**

```bash
# 1) Analyse the unrecognised PDF (local AI hints included by default;
#    add --no-ai ONLY if `rmu ai doctor` says local assets are unavailable)
uv run rmu onboard draft-profile path/to/new_vendor_report.pdf
# -> proposal: 1
#    draft:        store/drafts/onboard_1.yaml     (edit this)
#    review sheet: store/drafts/onboard_1.html     (open next to the PDF)
#    elements: header fields, record table + columns, per-record image
#    region, detection fingerprint - each with structural confidence,
#    evidence, and flags (low_confidence / non_generalising / orphan_image)

# 2) Review: set every element's review_state to confirmed / corrected
#    (+corrected_payload) / removed in the draft YAML. Approval is blocked
#    while anything stays 'proposed'.
uv run rmu onboard review 1 --regenerate-sheet

# 3) Approve = a machine-checked PROOF, not a signature: the corrected recipe
#    is re-extracted against the exemplar and must reproduce your confirmations
#    exactly; the fingerprint must match AND collide with no existing profile.
uv run rmu onboard approve 1 --as vendorx.pdf.survey@v1 --by <you>
# -> registered SourceProfile vendorx.pdf.survey@v1 (recipe = pure data,
#    run by the ONE generic engine; no per-profile code, ever)

# 4) The new shape now auto-detects; map it once, then batch-convert as usual:
uv run rmu map start --profile vendorx.pdf.survey@v1 \
  --template interim.defect_csv@1 --exemplar path/to/new_vendor_report.pdf
```

**B. Client target format arrives as a PDF → registered TargetTemplate:**

```bash
uv run rmu onboard draft-template path/to/client_defect_form.pdf
# fillable form  -> field schema proposed from the PDF's OWN declarations
#                   (required flags, kinds, option lists)
# fixed layout   -> labelled regions with page coordinates (text + photo boxes)
# encrypted/XFA/scanned -> rejected with a named condition + workaround,
#                   logged to store/onboard_rejections.jsonl

# review the draft YAML (fields/regions + per_record|per_batch cardinality), then:
uv run rmu onboard approve 2 --name clientx.defect_form@1 --by <you>
# approval test-renders sample values and must round-trip before registering

# batches now render filled PDFs - per record or per batch, read-back verified:
uv run rmu apply run ./batch \
  --transform "vendorx.pdf.survey@v1:clientx.defect_form@1"
# -> one filled PDF per record, every output round-trip verified
#    (values read back from the produced PDF must equal the records)
```

### Matrix targets (grid checklists)

Many client checklists are really a **two-dimensional map**: criteria down the
left (a number column paired with a text column), assets/towers across the top,
and every answer cell addressed by *both*. Onboarding such a PDF used to
produce hundreds of flat regions with positional names; now `draft-template`
reconstructs the **axes**:

```bash
uv run rmu onboard draft-template path/to/inspection_checklist.pdf
# grid detected -> the proposal contains:
#   row_axis   criteria entries  {id, number, label}   (~20 to review)
#   col_axis   tower entries     {id, label}           (~5 to review)
#   cells      one overlay region per blank answer slot, its name DERIVED
#              from the axes: corrosion__t2  ("Corrosion × T2")
```

- **Structure is deterministic** (pdfplumber grid geometry — the `--no-ai`
  floor is fully functional); the optional **interpret** stage adds AI
  suggestions for axis labels/structure. The model reasons over the extracted
  grid **plus the page image** but may only reference cells **by index** — a
  cited index that doesn't exist in the grid is dropped *and counted*, and a
  suggestion never overwrites a heuristic value. Suggestions surface as
  pending `suggested_*` hints the analyst confirms in review; nothing enters a
  registered template unconfirmed.
- **Local vision by default** — a dedicated `vision_model`
  (default `qwen2.5vl:7b`, loopback Ollama; `qwen3:4b` stays for the text
  tiers). `rmu ai doctor` reports its health. External vision remains
  consent-gated and is not yet enabled (D12, A14).
- The registered template's schema gains a `matrix` block (criteria, towers,
  cell-naming rule) as pure data; apply/verify/render are unchanged —
  approval still test-renders every cell round-trip.
- Tables that don't qualify as a matrix (too few rows/columns) still emit
  their fillable cells the old flat way — nothing is silently dropped.
- Rotated pages (the landscape-via-`/Rotate` case) reconstruct identically:
  detection runs derotated and cell coordinates map back to the visual space.
- In the Mapping Studio the proposal is reviewed **axis-first**: Criteria and
  Towers panels with pending AI suggestions, keyboard triage, and row/column
  highlight bands on the rendered page (see [Mapping Studio](#mapping-studio)).

**C. When SafeCard blocks a drifted document**, the exceptions report tells you
the recovery path — re-onboard as a delta:

```bash
uv run rmu onboard draft-profile drifted_report.pdf \
  --seed-from vendorx.pdf.survey@v1
# elements matching the known shape carry seed_match evidence; divergences are
# flagged seed_divergent - you review the delta, approve v2, nothing is guessed
```

The safety property throughout: a **draft can never be referenced by a batch
run** — only human-approved v1+ artifacts can (`DraftArtifactError` before a
single record is read), approval records who/when, and everything registered is
stored config, never generated code.

## CLI overview

| Command | Purpose |
|---|---|
| `rmu db init` / `rmu seed load` | Schema + idempotent data seeding |
| `rmu profile\|template\|valuemap list` | Registry inspection |
| `rmu valuemap create --name N --file F` | Insert a NEW version of a named lookup (append-only) |
| `rmu map start\|review\|preview\|approve` | The human-in-the-loop mapping session |
| `rmu map start --assist none\|local\|external [--client ID]` | Choose the assistance mode (default `local`) |
| `rmu map regenerate --session N` | Explicitly replace a session's proposals (prior set kept in history) |
| `rmu profile suggest <pdf>` | Suggest which registered profiles a document resembles |
| `rmu onboard draft-profile <pdf>... [--seed-from REF]` | Analyse an unrecognised source PDF into a draft extraction recipe (local-AI hints by default; `--no-ai` fallback) |
| `rmu onboard draft-template <pdf>` | Analyse a target PDF (form, fixed-layout, or grid checklist → criteria×tower matrix with optional local-vision interpret) into a draft template schema |
| `rmu onboard review\|approve\|abandon` | Per-element review; verify-on-approve registers the versioned artifact |
| `rmu ai doctor \| ai setup` | Local-AI health report / manual setup instructions |
| `rmu ai consent grant\|revoke\|list --client ID --by OWNER` | Record per-client external-API consent |
| `rmu apply run <folder> --transform REF... --answer k=v...` | Deterministic batch conversion; never interactive |
| `rmu apply regen <run-id>` | Exact regeneration of a past run, hash-verified |
| `rmu runs list\|show` | Audit-record inspection |

Exit codes: `0` success · `1` validation error (e.g. missing prompt answers,
empty batch) · `2` blocked (every document quarantined) · `3` approval
preconditions unmet · `4` external assistance refused (no recorded per-client
consent) · `5` requested assistance tier unavailable.

## How the mapping session works

1. `map start` extracts the exemplar and emits a **draft transform** (YAML,
   schema-validated) plus starter value-map files. In an assisted mode,
   proposals carry a confidence tier and one-line rationale, the draft banner
   lists a **ranked shortlist of candidate target fields** per source field, and
   unproposed required fields appear as unmapped placeholders.
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

## Local AI assistance

The mapping session can propose field routes and value maps **without any data
leaving the machine**. Assistance exists only inside the session; apply,
validate, render and audit are byte-for-byte unchanged, and AI never runs at
apply time (constitution rule 2).

Three modes, chosen in config or with `--assist` (default `local`):

- **`none`** — fully manual (`--no-ai` is an alias). Always works; this is the
  degradation floor.
- **`local`** (default, D8) — two tiers, both on-machine:
  - *tier 1* in-process CPU embeddings (`fastembed` + `BAAI/bge-small-en-v1.5`,
    A12a) rank candidate target fields per source field and power
    `rmu profile suggest`;
  - *tier 2* an optional loopback-only local LLM via Ollama (`qwen3:4b`, A12b,
    temperature 0, JSON-constrained) proposes value-map entries with rationales;
  - *vision (onboarding only)* an optional loopback-only local **vision** model
    (`vision_model`, default `qwen2.5vl:7b`, D12) powers the matrix-target
    interpret stage — axis structure/label suggestions by grid index, never
    coordinates.
  Tiers degrade independently — embeddings-only still gives ranking; with no
  assets installed the session behaves like `none`.
- **`external`** — third-party API, **refused unless** a per-client consent flag
  is recorded (`rmu ai consent grant --client <id> --by <owner>`). Consent is
  matched to an explicit `--client`; nothing is inferred (rule 7).

Every proposal is schema-validated then referent-checked; malformed or
unresolvable output is dropped and only ever shown as an aggregate count, never
surfaced as trusted. Proposals are generated once and persisted with provenance,
so re-opening a session never silently changes what is under review;
`rmu map regenerate` replaces them explicitly (prior set kept in history).

**Setup** (nothing downloads automatically — FR-014): `rmu ai setup` prints the
one-time steps; `rmu ai doctor` reports which tiers are ready. Tier 1 (embeddings)
is the `fastembed` model cache; tier 2 (LLM) needs a local Ollama with the model
pulled. Local assistance is sized for a personal CPU-only Apple-silicon machine
(A9); GPU-only models are out of scope.

```bash
uv run rmu ai setup                    # instructions (warm embeddings; optional:
                                       #   ollama pull qwen3:4b       - text proposals
                                       #   ollama pull qwen2.5vl:7b   - matrix-target vision interpret
uv run rmu ai doctor                   # per-tier health incl. the vision line; --json for scripts

# On-device proposals in a mapping session (local is the default mode):
uv run rmu map start --assist local \
  --profile scopito.pdf.powerline@v2020 --template interim.defect_csv@1 \
  --exemplar seed/source_samples/Distribution-report.pdf
uv run rmu map regenerate --session 1  # re-run proposals explicitly (prior set kept in history)

# Which known profile does a new document resemble? (embedding similarity)
uv run rmu profile suggest seed/source_samples/Report-Transmission.pdf

# External API is opt-in and refuses without a recorded per-client consent flag:
uv run rmu ai consent grant --client acme --by <you> --note "DPA signed"
uv run rmu map start --assist external --client acme \
  --profile scopito.pdf.powerline@v2020 --template interim.defect_csv@1 \
  --exemplar seed/source_samples/Distribution-report.pdf
```

If a tier is unavailable the session degrades cleanly rather than failing:
embeddings-only still ranks candidates; with no models installed at all,
`--assist local` behaves exactly like `--no-ai`.

**Proof it stays local:** `tests/integration/test_local_session_offline.py` runs
a full local-mode session with all non-loopback sockets blocked and still
produces proposals.

## Repository layout

```
src/rmu/
├── cli.py           # Typer CLI (`rmu`)
├── models.py        # 8 SQLAlchemy entities; append-only ★ tables
├── db.py            # engine/session + AppendOnlyViolation enforcement
├── store.py         # content-addressed blob store (store/objects/<sha>)
├── detect/          # profile fingerprint matching (anchors as data)
├── extract/         # per-profile parsers -> NormalizedRecords
├── mapping/         # HIL session, transform schema/loader, proposal providers, review sheet
├── onboard/         # assisted format onboarding: analyzers, proposal lifecycle, verify-on-approve
├── ai/              # local AI assist ONLY (embeddings, local LLM, config, consent, doctor)
├── apply/           # pure conversion engine + batch orchestration
├── validate/        # SafeCard scoring + template rule enforcement
└── render/          # deterministic CSV/docx/PDF rendering + round-trip verifier + OPC canonicalizer
templates/           # target formats as DATA (both INTERIM)
profiles/            # source-shape fingerprints + extraction anchors as DATA
seed/                # defect-code vocabulary + the two real Scopito demo PDFs
                     #   (seed/holdout/ = quarantined acceptance fixtures - never read by code)
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
uv run pytest                 # full suite (400+ tests; slow perf smoke: -m slow)
uv run pytest tests/invariants/   # the never-cut guarantees only
uv run ruff check src tests  # lint
```

Tests that need the local AI models auto-skip when the caches are absent, so the
suite is green on a fresh clone; install the models (`rmu ai setup`) to exercise
the on-device ranking and proposal paths.

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
data-processing agreement exists with that client. Three things enforce this:

- **On-device by default.** The `local` assistance mode runs entirely on the
  machine (in-process embeddings; an optional loopback-only local LLM) — no data
  leaves it, proven by a socket-blocked test. This lets AI assist on confidential
  reports *before* any external agreement exists.
- **External is consent-gated.** The `external` mode refuses to run unless an
  explicit per-client consent flag is recorded (`rmu ai consent grant`); nothing
  is inferred, and consent is matched to an explicit `--client`.
- **Manual always works.** The fully manual `--no-ai` path can never rot (it is
  the tested degradation floor), but it is the *fallback*, not the default: use
  it when `rmu ai doctor` says the local assets aren't available. The normal
  mode of operation is local AI.

The repo builds and tests exclusively on the bundled public demo PDFs and
synthetic fixtures, and AI is used only inside mapping sessions — never at apply
time, never on whole batches.

## Project documents

| Document | What it is |
|---|---|
| `docs/solution_design_mapping_v1.md` | The authoritative build spec (pipeline, HIL session, SafeCard, data model; §13 covers the v1.1 feature set) |
| `ASSUMPTIONS.md` | Numbered working assumptions (A1–A14) + decision log (D1–D12) |
| `STATUS.md` | Terse per-session build state, decisions, and DoD evidence |
| `specs/001-report-mapping-v1/` | Spec-kit artifacts for the v1 pipeline: spec, plan, research, data model, contracts, tasks |
| `specs/002-local-ai-assist/` | Spec-kit artifacts for the local AI assistance layer |
| `specs/003-pdf-format-onboarding/` | Spec-kit artifacts for assisted format onboarding (incl. recipe/template/proposal contracts) |
| `specs/004-mapping-studio/` | Spec-kit artifacts for the Mapping Studio (visual HIL surface) |
| `docs/superpowers/specs/2026-07-15-matrix-target-onboarding-design.md` | Approved design for matrix-aware target onboarding (feature 005; plan under `docs/superpowers/plans/`) |
| `scripts/acceptance_003.md` | The human-run SC-001 acceptance protocol for onboarding |
| `docs/eskom_dst34-1441_extraction.md` | Interim defect taxonomy source for the stand-in vocabulary |
| `.specify/memory/constitution.md` | The nine non-negotiable engineering principles this repo is governed by |
