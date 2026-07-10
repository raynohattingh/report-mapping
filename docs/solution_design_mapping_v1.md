# Solution Design — Report-Mapping Utility (v1)

**Date:** 2026-07-10 · **Status:** DESIGN — written ahead of build (pre-build task from `build_strategy_powerline.md`, pulled forward). Strategy source of truth: `build_strategy_powerline.md` (adopted 2026-07-10). Product concept: `idea_report_mapping_saas_2026-07-08.md`. Validation + kill thresholds: `idea-validation-report-mapping-saas-2026-07-10.md`.

**What this doc is:** the build spec for **v1, the mapping utility** — the first product. The classification engine is **v2** and has its own design (`solution_design_v0.md`) and its own held handoff kit (`handoff/`).

**What this doc is NOT:** a green light to start building ahead of the critical path. Critical path item #1 (get 3–5 real current-format source reports + the real Eskom target format; confirm the Scopito incumbent-gap) still decides whether v1 gets built at all (kill criterion #5). This design is written so that a FAIL on the Eskom side does not waste it — see §12 (graceful degradation).

---

## 1. Product definition

Given a **source report** (a drone-inspection export from Zeitview/Scopito — a bounded, enumerable set of known shapes) and a **target format** (Eskom Annexure H report pack; Eskom SAP-ready defect records), the utility performs an **AI-assisted, human-in-the-loop mapping ONCE**, stores it as a **versioned, reusable transform**, then **applies it automatically and deterministically to every subsequent report of the same shape**. Map one report; convert hundreds.

The contract, precisely:

```
detect(source_doc)            -> SourceProfile (or "unknown" -> HIL)
extract(source_doc, profile)  -> NormalizedRecords (typed field/record set)
map(profile, template)        -> Transform            # HIL session, ONCE per (profile, template) pair
apply(records, transform)     -> TargetDraft + ExceptionsReport
validate(draft, template)     -> SafeCard verdict (pass / warn / block)
render(draft, template)       -> output files (docx/xlsx/pdf/csv)
```

Everything left of `apply` is setup and may be expensive (human minutes, AI calls). Everything from `apply` rightward is runtime and must be **deterministic, near-zero-cost, and re-runnable byte-identically** (timestamps excepted). That asymmetry — expensive once, free thereafter — is the entire economic claim of the product; protect it in every design decision.

## 2. Scope

**In (v1):** document-to-document conversion only. Source = Zeitview/Scopito exports (PDF and, where available, CSV/API/structured exports). Target = Eskom-mandated formats (Annexure H pack, SAP defect records) once obtained; interim targets until then (§9). Batch processing. Stored transform library. HIL mapping session. Safe-card validation.

**Out (v1) — restating the locked rulings, do not re-litigate in the repo:**
- No SOE/government **portal** integration (SARS eFiling, CIPC, CSD, eTenders). Different product (RPA), different market.
- No generic industry-agnostic "any doc → any doc" mapper. Bounded profiles only; an unknown source is the *user's* one-time manual mapping job (input accountability sits with the user), never a promise of arbitrary parsing.
- No image classification, anomaly ML, or annotation UI — that is v2 and the platforms' job.
- No flight planning, no hosting platform, no wind/solar verticals.
- No multi-tenant SaaS infrastructure yet. v1 is single-operator (IAS-shaped): local or single-VM deployment. SaaS-ify with revenue, not before.

## 3. Vocabulary (used in code, docs, and DB)

| Term | Meaning |
|---|---|
| **SourceProfile** | A recognized source shape: platform × export kind × job type × structural version (e.g. `scopito.pdf.powerline.v2020`). Carries the extraction recipe. |
| **NormalizedRecords** | Typed output of extraction: one `ReportHeader` + N `FindingRecords` (+ assets manifest). Per-profile, NOT a universal ontology — see §5 ruling. |
| **TargetTemplate** | A target format definition: rendering template files (docx/xlsx) + required-field schema + validation rules. **Versioned, append-only, effective-dated.** |
| **Transform** | The stored mapping for one (SourceProfile, TargetTemplate) pair: field routes + value maps + constants + exception rules. **Data (YAML), not code. Versioned.** |
| **ValueMap** | A named, versioned lookup used by transforms: e.g. Scopito severity 1–5 → target priority vocabulary; platform issue labels → Eskom defect codes. |
| **MappingSession** | The HIL episode that produces or revises a Transform: AI proposals + human decisions, all persisted. |
| **ApplyRun** | One batch execution: inputs (doc hashes), transform version, template version, outputs, exceptions. The audit record that makes any past output regenerable. |
| **SafeCard** | The pre-apply mappability verdict + per-field confidence report (§7). |

## 4. Architecture

Pipeline stages, decoupled, each consuming/producing defined artifacts (same discipline as the v2 design):

```
[Detect] -> [Extract] -> [Map(HIL, once)] -> [Apply] -> [Validate/SafeCard] -> [Render] -> [Audit]
```

- **Detect:** fingerprint the incoming document against known SourceProfiles (structural signals: page-1 field labels, table headers, section titles — cheap heuristics first, AI fallback for ambiguity). Unknown profile → route to HIL, never guess silently.
- **Extract:** per-profile parser producing NormalizedRecords. PDF profiles use text/table extraction with per-profile anchors; structured exports (CSV/API) parse directly. Parsers are the only profile-specific *code*; everything downstream is data-driven.
- **Map:** the HIL mapping session (§6). Produces/updates a Transform.
- **Apply:** pure function `(NormalizedRecords, Transform) -> TargetDraft + Exceptions`. No AI calls, no network, no nondeterminism. This is the invariant that makes runtime free and outputs reproducible.
- **Validate:** target-template validation rules (required fields present, vocabulary values legal, cross-field checks) + SafeCard scoring.
- **Render:** TargetDraft → files via templates-as-data (docxtpl/openpyxl). Adding or revving a target format must never touch pipeline code.
- **Audit:** persist the ApplyRun. Requirement: any historical output regenerable exactly from (input hashes, transform version, template version).

**Boundary with v2:** a future vertical engine's only contract is "emit NormalizedRecords for some profile." The utility neither knows nor cares whether records came from a Scopito PDF or our own classification engine. Separate deployables; no shared internals.

## 5. Design ruling — no universal "schema G" up front

The idea note left open where the generic schema G comes from. Ruling for v1: **do not design a universal inspection ontology.** NormalizedRecords is a thin, per-profile extraction product (header + findings + assets) with a small shared core (structure/asset identifier, severity-as-source-vocab, label, free-text, geo if present, image refs). Reasons: (a) a universal schema designed against 2 platforms and 1 target is guaranteed wrong and becomes migration debt; (b) the transform layer already absorbs shape differences — that is its job; (c) v2 engines can emit the shared core natively. Generalize the core only when a third source family forces it. This is the same "earn generalisation" rule as the business scope, applied to the data model.

## 6. The HIL mapping session

Flow for a new (SourceProfile, TargetTemplate) pair:

1. Tool extracts one exemplar report and loads the target schema.
2. **AI proposes** a complete draft mapping: field routes, value maps, constants, unmapped-target-field list. Every proposal carries a confidence tier and a one-line rationale.
3. **Human reviews** the proposal side-by-side with the exemplar (interface: §6.1). AI proposals are visually distinct from human-confirmed decisions until accepted.
4. Human accepts / edits / rejects per field; fills unmapped required fields (constant, formula, or "ask-per-batch" prompt).
5. Tool applies the draft transform to the exemplar; human inspects the rendered output against the real target format.
6. On approval, the Transform is stored (version 1, effective-dated). Subsequent same-profile reports need **zero** human field decisions — only exception handling.

**Where the AI earns its place (and where it is banned):**
- AI does **semantic/value mapping**: severity-scale conversion (e.g. Scopito 1–5 → target priority vocabulary), platform issue-labels → defect-code vocabulary (`seed/defect_codes_v1.csv` is the interim target vocab), unit/date normalization, free-text → enum suggestions. These are proposals persisted for review, never silent conversions.
- Field-name routing barely needs AI — string/embedding similarity is a solved heuristic. Never let field-name match % masquerade as mapping confidence (§7).
- **Banned:** AI at apply time. Once a transform is approved, application is deterministic. If a value falls outside a ValueMap at apply time, it becomes an **exception** (flagged, human-resolved, optionally added to the ValueMap as a new versioned entry) — not an on-the-fly AI guess. Semantically-wrong-but-structurally-valid output is the product's worst failure mode because it looks finished.

**AI provider & data sensitivity:** Claude API on Rayno's personal account (Luno clearance: personal hardware/accounts/time). ⚠️ Client reports are IAS's (and ultimately Eskom's) confidential data — **before any real client report touches a third-party API, resolve data-processing consent with the client** (NDA offer to Dexter already made 2026-07-07). Design consequences: AI calls only in the mapping session (exemplar docs, not whole batches); a `--no-ai` mode must exist (pure-manual mapping session) so consent friction can never block delivery; build/test on the Scopito demo PDFs and synthetic fixtures, which carry no client data.

### 6.1 Interface decision — for the Sunday review

| | **Option A — CLI + reviewable artifacts** | **Option B — minimal local web UI** |
|---|---|---|
| Shape | Typer CLI; mapping proposal emitted as editable YAML + a generated static **HTML review sheet** (source exemplar, proposal, rationale, rendered preview side-by-side). Human edits YAML (or answers CLI prompts), re-runs, approves. | Small FastAPI + HTMX local app for the mapping-session step only; CLI still drives batch runs. |
| Build cost | Days. No frontend surface. Consistent with the v2 kit's stack. | +2–4 weeks realistically, solo, before Gate 2. A frontend to maintain forever after. |
| Fit for the buyer | Fine for v1's actual operator: IAS's geospatial team is technical. | Better *demo* to a room; friendlier for a non-technical reviewer. |
| Risk | YAML editing is error-prone → mitigated by schema validation + the review sheet + exemplar-render check (step 5). | Time risk to Gate 2; polish gravity (UI work expands to fill all time). |

**DECIDED 2026-07-10 (Rayno): Option A for v1.** The HTML review sheet gives 80% of Option B's demo value at ~5% of the cost, and the mapping session is a once-per-profile event, not a daily UI. Option B is a revenue-funded upgrade for a customer whose reviewers aren't technical — not a v1 requirement. The architecture is identical either way (the session produces the same stored Transform), so this is reversible later without rework.

## 7. SafeCard — semantic mappability scoring

Purpose: before a batch is applied (and during mapping), tell the user honestly whether the output can be trusted, and **block false comfort**.

Per-field confidence tiers (worst tier of any required field gates the verdict):

| Tier | Meaning |
|---|---|
| `T0 deterministic` | Human-confirmed route + closed ValueMap covering all observed values. |
| `T1 validated` | Human-confirmed route; ValueMap covers observed values with documented defaults for gaps. |
| `T2 proposed` | AI-suggested, not yet human-reviewed. **Never allowed in an approved transform.** |
| `T3 unmapped` | Required target field with no source. Needs constant/formula/per-batch prompt before approval. |

Batch-level SafeCard = (coverage: % of required target fields at T0/T1) × (value coverage: % of batch values falling inside ValueMaps) × (exception rate on this batch). Verdicts: **pass** (auto-apply), **warn** (apply, exceptions report prominent), **block** (structural drift suspected — e.g. extraction anchors missing → likely a new profile version; route to HIL). Explicit rule carried over from the concept doc: **field-name overlap % is never shown as a trust signal** — only value-level coverage is.

Every ApplyRun emits an **exceptions report** (per-record: what failed, why, suggested resolution) even on pass. The batch is never silently "all fine."

## 8. Data model

SQLAlchemy models; append-only + effective-dated where marked (regenerability rule: past ApplyRun outputs must be exactly regenerable — no destructive migrations on ★ tables).

- `SourceProfile` ★ — id, platform, export_kind, job_type, structural_version, detection fingerprint, extractor ref, status.
- `TargetTemplate` ★ — id, institution, name, version, effective_from, template files ref, required-field schema, validation rules.
- `Transform` ★ — id, source_profile_id, target_template_id, version, effective_from, YAML body, approval metadata (who/when), parent_version.
- `ValueMap` ★ — id, name, version, entries (source_value → target_value, provenance: human|ai-accepted, note).
- `MappingSession` — transform draft lineage: AI proposals, human decisions, timestamps. (Audit + the future training asset.)
- `SourceDocument` — hash, original filename, profile_id, received_at, extraction result ref.
- `ApplyRun` ★ — batch id, document hashes, transform version, template version, safecard verdict, outputs manifest, exceptions.
- `Exception` — apply_run_id, record ref, type, status (open/resolved), resolution (incl. ValueMap delta if any).

**Storage ruling: SQLite for v1** (via SQLAlchemy + Alembic, so Postgres is a config change later). Rationale: single operator, local deployment, no geospatial queries (unlike the v2 engine, which needs PostGIS), zero ops burden. Blob artifacts (source docs, outputs, review sheets) on disk in a content-addressed `store/` directory; DB holds hashes + metadata.

## 9. Targets and sources — what is real today vs TBD

**Sources (TBD-3, partially grounded 2026-07-10):** two real Scopito demo exports are in hand (project folder: `Distribution-report.pdf`, `Report-Transmission.pdf`). Observed structure (both): header block (inspection name, report date, type, company, image/annotation counts) → severity overview (Severity 1–5 + POI counts) → **annotation table** (`Id, Severity, User tags, Issues, Comments, Page`) → per-annotation image pages. Severity vocabulary confirmed as 1–5 + "?" (POI). ⚠️ Caveats: these are **2020 demo documents** — current Scopito export structure must be re-verified against fresh samples (the profile registry exists precisely because shapes drift); Zeitview samples: none in hand, least-public platform, deprioritized. Scopito also documents CSV/API exports publicly — the structured export, if IAS uses it, is a far better source than PDF and the trial-account route tests this without anyone's permission.

**Targets:** TBD-1 (Annexure H pro forma) and TBD-2 (SAP defect-record fields) are **not in hand**. NEVER invent their content. Interim targets, clearly labeled INTERIM in the template registry: (a) an Annex-C-style per-structure report pack modeled on the DST 34-1441 extraction, (b) a generic structured defect CSV using `defect_codes_v1.csv` as the target vocabulary. Both exist so the pipeline, HIL flow, and SafeCard can be built and demonstrated end-to-end; the real formats slot in as new TargetTemplate versions — data, not rewrites. (TBD-4, thermal spec, is v2-only and does not gate this build.)

## 10. Stack and conventions

Python 3.12 · uv · pytest (golden-file tests for rendering; property tests for apply determinism) · ruff · SQLAlchemy + Alembic on SQLite · Typer CLI · docxtpl + openpyxl · pdfplumber (primary PDF extraction; camelot/tabula only if tables defeat it) · anthropic SDK (mapping session only) · PyYAML + jsonschema (transform schema validation). Repo: `src/rmu/` (`detect/`, `extract/`, `mapping/`, `apply/`, `validate/`, `render/`, `cli.py`), `templates/`, `profiles/`, `seed/`, `store/`, `tests/`, `docs/`, `STATUS.md`. Type hints everywhere; small modules; no abstraction beyond the stage interfaces.

## 11. Definition of done + milestones

**v1 DoD (the map-once claim, made falsifiable):** given ≥20 same-profile source reports (real Scopito exports or faithful synthetic fixtures) and one approved Transform built from ONE exemplar: the remaining ≥19 convert with **zero human field decisions** (exceptions excepted, and exception rate reported); re-running the batch yields **byte-identical** target content (timestamps excepted); SafeCard + exceptions report produced; one deliberately-drifted input is **blocked**, not silently mis-mapped. Setup (mapping session) ≤ 2 hours human time per new profile-template pair.

- **M1 — scaffold + registries:** repo per §10, Alembic baseline, SourceProfile/TargetTemplate/Transform/ValueMap models + loaders, transform YAML schema + validator, seed loading (defect codes, interim templates). Tests.
- **M2 — extract:** `scopito.pdf.powerline` profile parser against the two real demo PDFs (committed as fixtures) + synthetic edge-case fixtures; detection fingerprinting; unmatched/unknown-profile path. Tests.
- **M3 — mapping session (HIL):** AI proposal generation, YAML draft + HTML review sheet, accept/edit/approve loop, `--no-ai` manual mode, Transform persistence. Exemplar-render check.
- **M4 — apply + SafeCard + render:** deterministic apply, ValueMap exceptions, SafeCard scoring/verdicts, interim-template rendering (docx/xlsx/csv), ApplyRun audit + regeneration command. Golden-file + determinism tests.
- **M5 — end-to-end + drift drill:** full batch run on fixtures meeting the DoD, including the drifted-input block case. Demo script for IAS (uses only demo/synthetic data).

## 12. Risks, open questions, graceful degradation

- **Kill criterion #5 (incumbent gap) is untested.** If Scopito's own customizable reporting reaches the Eskom format, v1's Eskom framing dies. The build survives: everything except the TargetTemplate contents transfers to (a) operator/EPC-format reporting automation or (b) any other institution — templates are swappable data from day one. That is why M1–M5 deliberately require zero Eskom-specific content.
- **PDF-as-source fragility** is the biggest technical risk. Mitigations: prefer structured exports (CSV/API) wherever the operator can produce them; per-profile extraction anchors + drift detection (SafeCard block); the profile registry treats a structural change as a *new profile version*, re-mapped once — which is the product working as designed, and the churn-moat pitch in miniature.
- **Build-timing decision (2026-07-10, Rayno):** v1 build starts the weekend of 11–12 Jul, AHEAD of the incumbent-gap test — overriding the earlier "sequenced behind critical path #1" position, to use the available build window. Risk accepted and bounded: the build contains zero Eskom-specific content (interim targets only), so a gap-test FAIL invalidates none of the engine. The gap test + Dexter escalation remain the top business actions from Monday 13 Jul. Weekend scope + working assumptions: `handoff_mapping_utility/ASSUMPTIONS.md`.
- **Open business questions (do NOT block the build):** pricing unit (per stored template / per seat / hybrid — "map once" argues against per-report); whether MappingSession data is contractually ours to keep per client (feeds the template-library moat — put it in the pilot agreement). §6.1 interface choice is DECIDED (Option A).
- **Escalation dependency:** fresh source samples + TBD-1/2 remain on the Dexter escalation clock (nudge ~14 Jul, phone by ~17 Jul, alternates in `build_strategy_powerline.md` §Contingency).
