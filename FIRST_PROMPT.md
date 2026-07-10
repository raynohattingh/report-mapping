# Weekend build runbook — Spec Kit + Claude Code (11–12 Jul 2026)

This is no longer a single paste-prompt: it is the **Spec-Kit-driven runbook** for the weekend. Every `/speckit.*` payload is pre-written below — the ceremony should cost minutes, not hours. Work top to bottom. Decisions are in `ASSUMPTIONS.md` (D1–D4); assumptions are A1–A8 — cite IDs in commits.

**Scope ruling for "working by Sunday" (A7):** one complete, tested, end-to-end vertical slice — real Scopito demo PDF in → detect → extract → HIL mapping session (Option A) → approved stored Transform → deterministic batch apply → SafeCard → rendered interim outputs → ApplyRun audit + regeneration. Invariant tests are non-negotiable (D3). Breadth (Zeitview, benchmarks, polish) is deferred, not dropped.

---

## 0 · Terminal setup (~5 min)

```bash
mkdir -p ~/dev/report-mapping
cp -R "/Users/raynohattingh/Documents/Claude/Projects/Comercial drone business/05_Software/handoff_mapping_utility/"{CLAUDE.md,ASSUMPTIONS.md,docs,seed} ~/dev/report-mapping/
cd ~/dev/report-mapping && git init

# Spec Kit (current CLI; if --integration is unrecognized on an older version, use --ai claude)
uvx --from git+https://github.com/github/spec-kit.git specify init . --integration claude

claude
```

Spec Kit artifacts (spec/plan/tasks) will live under its generated structure on feature branch `001-mapping-utility`; our `docs/solution_design_mapping_v1.md` remains the authoritative design — CLAUDE.md tells the agent how they relate.

## 1 · `/speckit.constitution` — paste exactly

```
/speckit.constitution This project (report-mapping utility "rmu") is governed by nine non-negotiable rules, already written in CLAUDE.md at the repo root — read that file and docs/solution_design_mapping_v1.md before drafting the constitution, and derive it from them. The load-bearing principles: (1) TBD discipline — the real Eskom Annexure H (TBD-1) and SAP defect fields (TBD-2) are NOT in hand; only the two INTERIM target templates may exist, behind the TargetTemplate registry; never invent Eskom content. (2) Apply is deterministic — no AI, no network, no nondeterminism at apply time; same inputs + transform version + template version = byte-identical output content (timestamps excepted); out-of-vocabulary values become logged exceptions, never guesses. (3) SourceProfile, TargetTemplate, Transform, ValueMap are versioned, append-only, effective-dated; any past ApplyRun must be exactly regenerable; no destructive migrations on these tables. (4) Templates and transforms are data (schema-validated YAML / template files), never code. (5) Field-name overlap is never a trust signal; SafeCard reports value-level coverage and human-confirmed tiers only. (6) Pipeline stages (Detect, Extract, Map, Apply, Validate, Render, Audit) stay decoupled. (7) No real client data to third-party APIs; build/test on seed demo PDFs and synthetic fixtures; a --no-ai mapping mode must always be fully functional. (8) TDD on the invariants: determinism, append-only enforcement, drift-block, exceptions reporting must have tests before features layer on. (9) Assumptions A1–A8 in ASSUMPTIONS.md are cited (A#) wherever code relies on them; new assumptions are logged there before use.
```

## 2 · `/speckit.specify` — paste exactly (WHAT only, no stack)

```
/speckit.specify Build the weekend slice of a report-mapping utility for drone-inspection operators. Problem: operators receive inspection reports from platforms (e.g. Scopito) and must re-deliver the same findings in a client's mandated format; today they re-do that conversion by hand for every report. The product maps a source report shape to a target format ONCE — AI-assisted with a human approving every mapping decision — stores that mapping as a reusable versioned transform, then converts every subsequent report of the same shape automatically with zero human field decisions.

User stories: (US1) As an analyst, I register a target format and run a one-time mapping session against ONE exemplar source report: the tool proposes field routes and value conversions (e.g. severity scale 1–5 to a priority vocabulary; free-text issue labels to a defect-code list), I review a side-by-side review sheet, accept/edit/reject each proposal, fill unmapped required fields with constants/formulas/per-batch prompts, verify a rendered preview of the exemplar, and approve — producing stored Transform v1. A fully manual mode (no AI) must accomplish the same session. (US2) As an analyst, I point the tool at a folder of same-shape reports and it converts the whole batch with zero field decisions: outputs are the target-format files plus a structured defect CSV, plus an exceptions report listing every record it could NOT confidently convert and why. (US3) As the responsible engineer, I can trust it: before applying, a "SafeCard" verdict tells me pass/warn/block based on value-level coverage (never field-name overlap); a structurally drifted input is BLOCKED, not mis-converted; re-running a batch reproduces byte-identical content; any past run is exactly regenerable from its recorded input hashes, transform version, and template version.

Acceptance (weekend DoD): from ONE exemplar of the bundled real Scopito demo reports, an approved transform converts a batch of at least 20 same-shape reports (the two real PDFs plus faithful synthetic same-structure fixtures) with zero human field decisions; one deliberately drifted fixture is blocked; determinism and regeneration are proven by tests, not by demonstration. Out of scope this weekend (deferred, not dropped): any second source platform, real Eskom formats (interim stand-in templates only — the real ones arrive later as data), web UI, multi-user/SaaS anything, image classification.
```

## 3 · `/speckit.clarify` — paste exactly

```
/speckit.clarify Before asking me anything: read ASSUMPTIONS.md (assumptions A1–A8, decisions D1–D4) and docs/solution_design_mapping_v1.md — most ambiguities are already resolved there; do not re-open decided items (D1 interface, D4 storage, degradation order D3). Only surface genuine gaps that block the plan. If a gap is real and I am not available, make the most conservative choice consistent with the constitution, and append it to ASSUMPTIONS.md as a new numbered assumption with blast radius and clearance route.
```

Then run `/speckit.checklist`. Fix what it flags in the spec; don't argue with it.

## 4 · `/speckit.plan` — paste exactly

```
/speckit.plan docs/solution_design_mapping_v1.md is the authoritative design — conform to it and list any deviation explicitly at the top of the plan. Stack: Python 3.12 managed by uv; Typer CLI (`rmu`); SQLAlchemy + Alembic on SQLite (Postgres-ready by config; append-only enforcement at the model layer for SourceProfile/TargetTemplate/Transform/ValueMap); pdfplumber for PDF extraction; PyYAML + jsonschema for the Transform format; docxtpl + openpyxl for rendering; Jinja2 for the static HTML review sheet; anthropic SDK behind a provider interface used ONLY in the mapping session and only when --no-ai is not set; pytest with golden-file tests for rendering and property/determinism tests for apply; ruff. Package layout: src/rmu/{detect,extract,mapping,apply,validate,render}/ plus cli.py; templates/, profiles/, seed/, store/ (content-addressed blobs, gitignored), tests/, docs/, STATUS.md. Data model per design §8: SourceProfile, TargetTemplate, Transform, ValueMap (all versioned/append-only/effective-dated), MappingSession, SourceDocument, ApplyRun, Exception. Pipeline per design §4 with apply as a pure function. Extraction targets profile scopito.pdf.powerline.v2020 built against the two real PDFs in seed/source_samples/ (assumption A1; severity vocab per A3). Interim targets per design §9 and assumption A2, seeded from seed/defect_codes_v1.csv and docs/eskom_dst34-1441_extraction.md. Structure the plan in four phases matching the weekend: P1 scaffold+registries+transform schema, P2 extraction+detection+fixtures, P3 mapping session (manual --no-ai path FIRST, AI proposals second, HTML review sheet third — that is the cut order if time runs out, per D3), P4 apply+SafeCard+render+audit+end-to-end drift drill.
```

## 5 · `/speckit.tasks` then `/speckit.analyze`

Run both. `/speckit.analyze` must come back clean (or with accepted notes) **before** implementing — with a 2-day window you cannot afford task-level rework from a spec/plan mismatch. If analyze flags a conflict with the design doc, the design doc wins; fix the spec/plan artifact.

## 6 · `/speckit.implement` — phased, with checkpoints

Do NOT run one giant implement. Implement per phase, committing at each checkpoint:

| When | Phase | Checkpoint = commit + STATUS.md update |
|---|---|---|
| Sat AM | P1 | Registries migrate, seed loaders pass (incl. A6-row validation), transform YAML round-trips, append-only enforcement TESTED |
| Sat PM | P2 | Both real PDFs extract to NormalizedRecords; drifted synthetic fixture routed to unknown/blocked; fixture batch ≥20 generated |
| Sat eve / Sun AM | P3 | Manual `--no-ai` mapping session end-to-end → approved Transform v1 for (scopito.v2020 → interim template); then AI proposals; then review sheet |
| Sun PM | P4 | Full batch run meets the weekend DoD incl. drift-block, determinism + regeneration tests green; tag `v0.1.0-slice` |

If a phase overruns: apply D3's cut order inside P3; never touch the P1/P4 invariants. After each phase, `/speckit.analyze` again if the plan drifted, else continue.

## 7 · End of weekend

STATUS.md final entry: DoD items met/missed, assumptions added, exact next actions (Zeitview profile? fresh Scopito samples per A1? IAS demo script?). Business side reads it at the next review. Monday is discovery again: Dexter nudge (~14 Jul) and the incumbent-gap test remain the top business actions — a working slice makes that conversation stronger, it does not replace it.
