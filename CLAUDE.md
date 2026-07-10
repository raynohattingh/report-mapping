# Report-Mapping Utility (v1 — the current first build)

Converts drone-inspection source reports (Zeitview/Scopito exports — a bounded set of known shapes) into a client's mandated target format (Eskom Annexure H pack + SAP-ready defect records, once obtained; interim formats until then). The mapping is made ONCE per (source profile, target template) pair — AI-assisted, human-in-the-loop — stored as a versioned transform, then applied deterministically to every subsequent same-shape report. Map one, convert hundreds.

Solo-founder project (Rayno), pre-revenue, building toward a paid pilot with Integrated Aerial Systems (IAS) by 2026-08-30 (Gate 2). This utility is **v1** of the version ladder; the classification engine is **v2** (separate design + held kit — do not build any of it here).

## Read before coding

- `docs/solution_design_mapping_v1.md` — THE build spec: contract, pipeline, HIL mapping session, SafeCard, data model, milestones M1–M5, definition of done. Follow it; propose changes in STATUS.md rather than silently deviating.
- `ASSUMPTIONS.md` — numbered educated assumptions (A1–A8) + decisions (D1–D4) made 2026-07-10 to unblock the build. Cite `A#`/`D#` in code comments and commits wherever relied upon. New assumptions get logged there BEFORE use.
- **Spec Kit:** this repo uses GitHub Spec Kit (`/speckit.*` artifacts on feature branches). Precedence on conflict: this CLAUDE.md's hard rules > `docs/solution_design_mapping_v1.md` > Spec Kit spec/plan/tasks artifacts. If a speckit artifact drifts from the design doc, fix the artifact, not the design.
- `docs/eskom_dst34-1441_extraction.md` — the Eskom defect taxonomy used as the INTERIM target vocabulary.
- `seed/defect_codes_v1.csv` — interim defect-code table (A1–F12 + T/V placeholders). Load as data, never hardcode.
- `seed/source_samples/` — two REAL Scopito demo exports (distribution + transmission powerline). These are the primary extraction fixtures. ⚠️ 2020 demo documents: treat their structure as profile `scopito.pdf.powerline.v2020`; current exports may differ — that's what the profile registry is for.

## Hard rules

1. **TBD discipline — never invent unresolved interface content.** TBD-1 (Annexure H pro forma) and TBD-2 (SAP defect-record fields) are NOT in hand. Build only the INTERIM targets defined in design §9, behind the TargetTemplate registry, so real formats slot in as data. If a task seems to need TBD content, stop and flag in STATUS.md.
2. **Apply is deterministic. No AI at apply time, ever.** AI lives only in the mapping session, as persisted proposals a human reviews. Out-of-vocabulary values at apply time become exceptions, not guesses. Same inputs + same transform version + same template version → byte-identical output content (timestamps excepted).
3. **Transforms, ValueMaps, TargetTemplates, SourceProfiles are versioned, append-only, effective-dated.** Any past ApplyRun must be exactly regenerable. No destructive migrations on these tables.
4. **Templates and transforms are data, not code.** Adding a target format or revising a mapping must never touch pipeline code. Transform YAML is schema-validated.
5. **Never present field-name overlap as confidence.** SafeCard trust signals are value-level coverage + human-confirmed tiers only (design §7). Semantically-wrong-but-structurally-valid output is the worst failure mode.
6. **Pipeline stages stay decoupled** (Detect → Extract → Map → Apply → Validate → Render → Audit); no stage reaches around another. A future v2 engine talks to this tool only via NormalizedRecords.
7. **Data sensitivity:** real client reports must not be sent to any third-party API until data-processing consent exists with that client. Build and test on the seed demo PDFs + synthetic fixtures only. A `--no-ai` mapping mode must always work.
8. Update `STATUS.md` at the end of every working session: done, decisions, next, open questions. It is how the business side (separate Claude desktop workspace) tracks build state — current and terse.
9. Personal project: personal hardware, personal accounts, personal time only. No employer resources, ever.

## Stack and conventions

Python 3.12, uv, pytest (golden-file tests for rendering, determinism tests for apply), ruff, SQLAlchemy + Alembic on **SQLite** (Postgres-ready by config), Typer CLI, docxtpl + openpyxl, pdfplumber for PDF extraction, anthropic SDK (mapping session only), PyYAML + jsonschema. Structure: `src/rmu/` (`detect/`, `extract/`, `mapping/`, `apply/`, `validate/`, `render/`, `cli.py`), `templates/`, `profiles/`, `seed/`, `store/`, `tests/`, `docs/`, `STATUS.md`. Type hints everywhere; small modules; no premature abstraction beyond the stage interfaces.

## v1 definition of done (Gate-2 demo)

From ONE exemplar report a human-approved transform is built (≤2h human setup); ≥20 same-profile reports then convert with zero human field decisions (exceptions reported, not silently absorbed); re-runs are byte-identical; a deliberately structure-drifted input is BLOCKED by SafeCard, not mis-mapped; every batch emits an exceptions report. Demo uses only demo/synthetic data.

## Milestones

M1 scaffold + registries → M2 Scopito PDF extraction + profile detection → M3 HIL mapping session (Option A per D1: CLI + YAML + HTML review sheet, `--no-ai` mode is the core path) → M4 deterministic apply + SafeCard + interim rendering + audit → M5 end-to-end batch + drift drill + IAS demo script. Full acceptance criteria in design doc §11. **Weekend 11–12 Jul target (A7):** M1–M4 as a complete vertical slice + the M5 drift drill; cut order under time pressure is D3 in ASSUMPTIONS.md — invariants and their tests are never cut.

When a TBD resolves (spec files arrive in `docs/` as `spec_update_*.md`), read the file, propose the delta in STATUS.md, then implement as template/data changes first.

<!-- SPECKIT START -->
Active feature plan: specs/001-report-mapping-v1/plan.md (spec: specs/001-report-mapping-v1/spec.md)
<!-- SPECKIT END -->
