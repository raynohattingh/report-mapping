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

## v1.1 additions (2026-07-11)

| ID | Assumption | Blast radius if wrong | How to clear |
|---|---|---|---|
| **A9** | Build/run hardware = Rayno's personal Apple-silicon Mac, ≥16GB unified memory, no discrete GPU. Local AI sized accordingly: small embedding model + ≤~4B-param instruct model via Ollama. | Model config change only (tiers are config, D8). | Confirm machine specs; adjust `rmu ai doctor` expectations. |
| **A10** | The document-anatomy approach (pdfplumber primitives: positioned words, tables, font clustering, repeated rows) is sufficient to draft profiles for the *digitally-generated, structured* PDFs operators actually export. Scanned/image PDFs are out of scope. | If real operator PDFs are messier than assumed, draft quality drops — HIL correction absorbs it (that's why approval is mandatory, D5); OCR becomes a logged future feature. | First 3–5 real current-format reports (same clearance as A1). |
| **A11** | Eskom-style mandated target formats will be fillable-form or fixed-layout PDFs (or docx/xlsx already supported) — covered by D7's pdf_form + pdf_overlay kinds. | A target outside these kinds needs a new render backend; registries/transforms unaffected. | TBD-1 landing (real Annexure H in hand). |
| **A12** | Specific local model choices (embedding + instruct) are resolved by Claude Code AT BUILD TIME from the then-current Ollama/sentence-transformers ecosystem (web-search quota blocked verification on 2026-07-11); chosen names + licenses must be recorded here as A12a/A12b when picked. | Config swap. | Build-time selection + periodic re-check. |
| **A12a** | Tier-1 embeddings = `fastembed` (Apache-2.0) running `BAAI/bge-small-en-v1.5` (MIT, 384-dim), in-process ONNX on CPU — **installed 002 build: fastembed 0.8.0, model cache warmed; SC-002 measured 100% top-3** on the seed ground truth. Forced HF offline mode so a missing cache degrades instead of downloading (FR-014). | Config swap (D8); ranking eval (SC-002) re-run against replacement. | Re-verify license + availability at `uv add` time; revisit if SC-002's 90% top-3 fails. |
| **A12b** | Tier-2 local LLM = Ollama `qwen3:4b` (Apache-2.0), temperature 0, JSON-constrained; documented fallback `gemma3:4b`. **Build revision: client is stdlib `urllib` against the loopback URL, NOT the `ollama` package** (fewer deps, explicit loopback pin — research.md R2). Ollama runtime is an optional user install (`rmu ai setup`); absent ⇒ per-tier degradation. | Config swap (D8); proposal-quality drop absorbed by HIL review (nothing auto-accepted). | Re-verify at `ollama pull` time; revisit on A9 memory/latency pressure (SC-008). |

## Decision log (made 2026-07-10, previously parked — cite as D#)

- **D1** HIL interface = Option A (CLI + YAML + generated HTML review sheet). Design doc §6.1.
- **D2** Build starts 11–12 Jul weekend, ahead of the incumbent-gap test (Rayno's override; risk bounded — zero Eskom-specific content in the build). Design doc §12.
- **D3** Degradation order if Saturday slips: cut AI-assist (manual `--no-ai` mapping is the core path), then HTML review-sheet polish (plain YAML review), then the second interim template. NEVER cut: apply determinism, append-only registries, drift-block, exceptions report, or their tests — those are the product's claims.
- **D4** Storage = SQLite (design §8). Pricing/data-ownership stay open as business questions; they do not gate the build.

## Decision log — v1.1 (2026-07-11)

- **D5** Features "ingest any source/target PDF → auto-create profile/template" are built as **assisted onboarding**: tool proposes a DRAFT, human validates/approves in HIL, draft artifacts can never be used by an ApplyRun. Fully-unattended any-doc conversion stays rejected (scope ruling, idea note 2026-07-10). Design §13.1.
- **D6** Mapping Studio (local FastAPI+HTMX+PDF.js web app) approved as the primary HIL surface — **reverses D1's Option-A-only** on new information: the engine now exists, and profile/template onboarding is inherently visual. CLI remains canonical for batch; single-write-path rule (studio owns zero business logic). Design §13.2.
- **D7** PDF-target rendering = AcroForm fill (`pdf_form`) + coordinate overlay via reportlab (`pdf_overlay`) first; HTML→PDF reconstruction deferred. Overflowing values are exceptions, never silent truncation.
- **D8** Local AI = tiered: (1) CPU embeddings for field-routing candidates + fingerprint similarity, (2) optional local LLM via Ollama for value-map proposals (temp 0, strict JSON), (3) external API opt-in gated on a recorded per-client consent flag. Model names are config resolved at build time (A12). AI at apply time remains banned (constitution rule 2).
- **D9** Build order 002-local-ai → 003-onboarding-assist → 004-mapping-studio; all of v1.1 stays SEQUENCED BEHIND Monday's discovery actions (Dexter nudge, incumbent-gap test) — features don't monetise an unsold product.

## Decision log — 003 build (2026-07-12)

- **D10** Stack extension for 003 (constitution "fixed stack" carve-out, justified in specs/003-pdf-format-onboarding/plan.md Complexity Tracking): `pypdf` added as runtime dependency (AcroForm enumerate/fill/read-back, encryption + XFA detection); `reportlab` promoted from dev to runtime dependency (fixed-layout text/image overlay per D7). Rejected: pdfrw (unmaintained), pikepdf (C++ wheel), external pdftk (non-Python runtime), hand-built content streams. Cite D10 in code/commits that rely on these libs.

## v1.1 additions — 004 build (2026-07-14)

| ID | Assumption | Blast radius if wrong | How to clear |
|---|---|---|---|
| **A13** | A modern desktop browser (Chrome/Edge/Firefox/Safari current at build time; ES-module + canvas support sufficient for PDF.js) is available on the analyst machine (extends A5/A9). No minimum version is pinned; the vendored PDF.js build's own floor governs. | Studio unusable in that browser — CLI path (canonical, always functional) is the fallback; vendored PDF.js/HTMX can be swapped for older builds as a data/asset change. | First session on the actual pilot machine (Gate-2 demo prep). |

## Decision log — 004 build (2026-07-14)

- **D11** Stack extension for 004 (constitution "fixed stack" carve-out, justified in specs/004-mapping-studio/plan.md Complexity Tracking): `fastapi` + `uvicorn` + `python-multipart` added as an **optional `studio` dependency group** (`uv sync --group studio`) so the core install is unchanged and "suite green without the studio" (FR-042) is a real installation state; `htmx` and `pdf.js` are **vendored as pinned static assets inside `src/rmu/studio/static/vendor/`** (no CDN — the studio must work with zero network access; assets ship inside the deletable package). Rejected: stdlib `http.server` (hand-rolled routing/multipart/middleware = more security-sensitive code), Flask (no typed contract benefit; D6 names FastAPI), SPA framework + build toolchain (client-side state violates the zero-business-logic rule; FR-004). Cite D11 in code/commits that rely on these deps.
