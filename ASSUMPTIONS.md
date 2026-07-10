# ASSUMPTIONS.md — educated assumptions made 2026-07-10 to unblock the weekend build

Rule: every assumption here was made deliberately because the real answer was unobtainable on 2026-07-10. Each has an ID (cite it in code comments/commits as `A#`), a blast radius, and a clearance route. When one clears, update this file AND grep the repo for its ID. Do not silently add assumptions — new ones get logged here first.

| ID | Assumption | Blast radius if wrong | How to clear |
|---|---|---|---|
| **A1** | Current Scopito PDF exports share the structure of the 2020 demo reports in `seed/source_samples/` (header block → severity 1–5/POI overview → annotation table `Id, Severity, User tags, Issues, Comments, Page` → per-annotation pages). | Extraction parser for profile `scopito.pdf.powerline.v2020` needs a new profile version; engine unaffected (that path is the product working as designed). | Fresh export samples from IAS (Dexter, escalation clock: nudge ~14 Jul, phone ~17 Jul) or a Scopito trial account. |
| **A2** | The two INTERIM target templates (Annex-C-style report pack modeled on `docs/eskom_dst34-1441_extraction.md`; generic defect CSV using `seed/defect_codes_v1.csv`) are structurally representative of the real targets — i.e. the real Annexure H (TBD-1) and SAP defect fields (TBD-2) will slot in as new TargetTemplate versions without pipeline changes. | If the real formats need capabilities the renderer lacks (e.g. embedded image layouts, multi-sheet cross-refs), Render stage grows; registries/transforms unaffected. | TBD-1/TBD-2 documents from IAS or alternates (contingency table in `build_strategy_powerline.md`). |
| **A3** | Scopito severity vocabulary is exactly `1–5` + `?` (POI), per the demo reports. | ValueMap for severity gets new entries — data change only. | Same as A1. |
| **A4** | PDF is the source medium for v1. Scopito's structured CSV/API export (publicly documented) may be what IAS actually uses — which would be a BETTER source. | Extraction layer swaps per profile; Detect/Map/Apply untouched (extraction is isolated by design). | Ask IAS which export they pull; Scopito trial account test. |
| **A5** | Single-operator, local/single-machine deployment (SQLite, `store/` on disk) is sufficient for v0/v1 pilot. | Postgres is a config change (SQLAlchemy+Alembic); multi-tenant is a v3 concern. | Pilot terms with first customer. |
| **A6** | AI provider = Anthropic API on Rayno's personal account; used ONLY in mapping sessions on demo/synthetic data until client consent exists. `--no-ai` path is fully functional. | None to the engine — AI is an enhancement layer by design. | Client data-processing consent (NDA thread with Dexter). |
| **A7** | The weekend slice (see FIRST_PROMPT §Scope) is what "working by Sunday 12 Jul" means: one profile, two interim targets, full pipeline, invariant tests. Deferred, NOT dropped: second source profile (Zeitview), ≤2h-setup human benchmark, M5 IAS demo script polish, extraction hardening beyond the demo PDFs + synthetic drift fixtures. | — | Reviewed at next weekly review against v1 DoD (design §11). |
| **A8** | Transform YAML authored/edited by a technical user is acceptable UX for v1 (HIL Option A — DECIDED 2026-07-10, no longer open). | Web UI (Option B) is a bolt-on later; stored Transform format identical. | First non-technical reviewer at a paying customer. |

## Decision log (made 2026-07-10, previously parked — cite as D#)

- **D1** HIL interface = Option A (CLI + YAML + generated HTML review sheet). Design doc §6.1.
- **D2** Build starts 11–12 Jul weekend, ahead of the incumbent-gap test (Rayno's override; risk bounded — zero Eskom-specific content in the build). Design doc §12.
- **D3** Degradation order if Saturday slips: cut AI-assist (manual `--no-ai` mapping is the core path), then HTML review-sheet polish (plain YAML review), then the second interim template. NEVER cut: apply determinism, append-only registries, drift-block, exceptions report, or their tests — those are the product's claims.
- **D4** Storage = SQLite (design §8). Pricing/data-ownership stay open as business questions; they do not gate the build.
