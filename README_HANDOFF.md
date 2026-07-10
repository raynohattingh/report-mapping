# Handoff kit → Claude Code — Report-Mapping Utility (v1, the current first build)

Built 2026-07-10 (day of the reframe adoption). Everything Claude Code needs to start the **v1 mapping utility** warm. This kit supersedes nothing: the sibling `../handoff/` kit is the **v2 classification engine**, held for that phase — the two kits build different products into different repos.

> **Timing decision (D2, 2026-07-10):** build starts the weekend of 11–12 Jul, AHEAD of the incumbent-gap test — Rayno's call, risk bounded (zero Eskom-specific content in the build). The gap test + Dexter escalation (~14 Jul) remain the top business actions from Monday.

## Setup — Spec Kit workflow

The build runs on **GitHub Spec Kit** inside Claude Code. `FIRST_PROMPT.md` is the full weekend runbook: terminal setup (`specify init . --integration claude`), then pre-written payloads for `/speckit.constitution → specify → clarify → checklist → plan → tasks → analyze → implement`, phased Sat/Sun with commit checkpoints. Work it top to bottom; don't freestyle past a failed `/speckit.analyze`.

## What's in the kit

| File | Purpose |
|---|---|
| `CLAUDE.md` | Auto-loaded every session: product context, 9 hard rules (TBD discipline, deterministic apply, versioned registries, transforms/templates-as-data, SafeCard honesty, data sensitivity, STATUS.md upkeep), stack, milestones, DoD |
| `docs/solution_design_mapping_v1.md` | THE build spec (snapshot; canonical copy in `05_Software/`) |
| `docs/eskom_dst34-1441_extraction.md` | Interim target vocabulary (Eskom defect taxonomy) |
| `seed/defect_codes_v1.csv` | Interim defect-code table, versioned, ready for the loader |
| `seed/source_samples/` | Two REAL Scopito demo exports (distribution + transmission) — the primary extraction fixtures. 2020 demos; treat as profile `…v2020` (assumption A1) |
| `ASSUMPTIONS.md` | Educated assumptions A1–A8 + decisions D1–D4 with blast radius and clearance routes — cite IDs in commits; clear them as real data lands |
| `FIRST_PROMPT.md` | The Spec Kit weekend runbook: setup + paste-ready payloads for every `/speckit.*` phase + Sat/Sun checkpoints |

## The working loop between the two tools

- **Claude Code (terminal, ~/dev/report-mapping):** all code. Maintains `STATUS.md` per session — that file + `git log` is the build's state of record.
- **Claude desktop (this workspace):** business side — strategy, discovery, findings log, TBD intake, weekly review, tender watch.
- **Spec changes flow one way:** when a TBD resolves (Dexter sends Annexure H / SAP fields / fresh exports), the desktop side extracts it into `spec_update_<topic>_<date>.md`; drop it into the repo's `docs/` and tell Claude Code to read it and propose the delta in STATUS.md.
- **Build state flows back** at the Sunday review: read STATUS.md (connect ~/dev/report-mapping to the session, or paste it).

## Reminders

- After handoff the repo's `docs/` copy is canonical for code questions; `05_Software/` is canonical for business questions. Flag drift at the Sunday review.
- HIL interface: **DECIDED (D1)** — Option A, CLI + YAML + HTML review sheet. No open build decisions remain; open business questions (pricing, mapping-data ownership) do not gate the build.
- Personal hardware, personal accounts, personal time (Luno clearance condition, resolved 2026-07-07).
- No real client report to any third-party API before data-processing consent with that client (CLAUDE.md rule 7).
