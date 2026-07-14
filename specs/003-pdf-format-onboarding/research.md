# Research: PDF Format Onboarding (003)

All Technical Context unknowns resolved. Decisions below carry rationale and rejected alternatives.

## R1 — PDF form manipulation library

**Decision**: `pypdf` for AcroForm field enumeration (`PdfReader.get_fields()`), fill (`PdfWriter.update_page_form_field_values`), read-back (re-open and `get_fields()`), encryption detection (`PdfReader.is_encrypted`), and XFA detection (`/AcroForm` dict containing `/XFA` key).

**Rationale**: pure-Python, maintained, already the de-facto standard; covers every form-side FR (FR-006/007/011/013) plus the FR-010 diagnoses with one dependency. `NeedAppearances` must be set on fill so viewers regenerate field appearance streams — without it filled values may not display; round-trip read-back is unaffected either way, but the golden tests assert we set it.

**Alternatives considered**: `pdfrw` (unmaintained since 2017); `pikepdf` (qpdf bindings — powerful but C++ wheel dependency and lower-level form API); external `pdftk` (non-Python runtime dep, violates single-operator local simplicity).

## R2 — Fixed-layout overlay rendering

**Decision**: `reportlab` draws each page's values (text via `drawString`, images via `drawImage` with `preserveAspectRatio=True, anchor='c'`) onto an in-memory overlay PDF; `pypdf` merges overlay pages onto the original template pages (`PageObject.merge_page`). Fonts: embedded core Helvetica at a size declared per region in the template config (default 9pt) — real text, so pdfplumber can read it back for FR-013/SC-005.

**Rationale**: the only pure-Python combination that yields *extractable text* at exact coordinates (raster overlays would defeat round-trip verification). Image scale-to-fit-no-crop (FR-012a) is a reportlab one-liner.

**Alternatives considered**: hand-built content streams via pypdf (fonts/encoding minefield); fpdf2 (would work for the overlay but adds a second PDF-writing dep for no capability reportlab lacks); rasterizing values (breaks FR-013 text read-back).

## R3 — Source-structure heuristics (draft-profile analysis)

**Decision**: pdfplumber geometry, three passes, all deterministic:
1. **Page anatomy** — cluster words recurring at near-identical y-positions across ≥60% of pages → header/footer furniture, excluded from record detection.
2. **Table/record detection** — `page.find_tables()` for ruled tables; for unruled layouts, x-position clustering of word columns across consecutive lines (same technique the scopito extractor uses, generalized); repeated line-signatures (same column pattern, ≥3 occurrences) → record rows; the line above a run with distinct token set → column header candidates.
3. **Header-field detection** — first-pages text matching `Label: value` / stacked-label patterns → key-value candidates.

Confidence per element = structural evidence score (recurrence count, alignment tightness, cross-exemplar agreement when extras supplied) — never name similarity (Constitution V). Image regions: `page.images` bboxes correlated to record row bboxes by y-overlap → per-record image elements (FR-001a).

**Rationale**: reuses proven techniques from the existing hand-built extractor; fully offline; measurable against the ≥80% bar. Multi-exemplar cross-check (FR-001) = run passes per exemplar, intersect element sets, down-score non-generalising elements.

**Alternatives considered**: camelot/tabula (Java dep or ghostscript dep; weaker on unruled layouts); LLM-first analysis (violates determinism-of-base-proposal decision and SC-009 budget on 300 pages).

## R4 — Local-AI enrichment integration

**Decision**: reuse the 002 layer (`rmu.ai`) exactly as the mapping session does: enrichment proposes *names/labels/matches* for already-detected elements (never new structure), is persisted into the proposal with provenance, and is skipped entirely under `--no-ai`. Page sampling for SC-009: enrichment sees at most N representative pages (first, last, densest-table page, plus one per distinct page-signature cluster), not all 300.

**Rationale**: keeps heuristics as the sole source of structure (FR-020), bounds LLM time, and reuses existing config/doctor plumbing.

**Alternatives considered**: letting the LLM propose regions (unbounded, unverifiable against structure); cloud AI (excluded by clarification).

## R5 — Recipe-driven generic extraction

**Decision**: new `rmu.extract.recipe_pdf` engine interpreting a schema-validated recipe YAML (contracts/recipe.schema.json): fingerprint block (same dict schema `detect/fingerprint.py` already matches), header-field lookups (label + position strategy), record-table spec (column x-ranges or ruled-table index, row pattern, page range), image-region spec. Registered onboarded profiles set `extractor_ref: rmu.extract.recipe_pdf`; the existing registry row shape is unchanged (recipe lives in the profile YAML file, like scopito's anchors do today).

**Rationale**: SourceProfile already separates data (`profiles/*.yaml`) from `extractor_ref`; adding ONE generic engine honors "per-profile parsers are the only profile-specific code" by eliminating the need for further per-profile parsers (Constitution IV/VI).

**Alternatives considered**: generating Python extractor code per profile (explicitly forbidden — US4 "stored config, not generated code"); extending the scopito extractor with branches (couples unrelated shapes).

## R6 — Draft storage & the ApplyRun guard

**Decision**: new non-registry table `onboarding_proposals` (mirrors `mapping_sessions`: status draft|approved|abandoned, JSON elements, provenance) + proposal YAML in `store/drafts/` while editable. Approval writes the registry row (+ `profiles/*.yaml` for source recipes) and stamps the proposal `approved` with `resulting_*_id`. The ApplyRun guard (FR-016): apply resolves profiles/templates ONLY from registries — plus an explicit pre-flight check that any CLI-supplied artifact reference resolves to a registered row, else `DraftArtifactError` naming the artifact and its status, emitted before any record is read.

**Rationale**: drafts structurally cannot be applied (they're not in the registries), and the explicit check turns a silent "not found" into the clear error SC-006 demands.

**Alternatives considered**: draft rows inside the registry tables with a status column (pollutes append-only ★ tables and makes the guard a filter instead of a wall).

## R7 — XFA / encryption / scanned detection order

**Decision**: `pdf_kind.py` diagnosis ladder, first match wins: (1) not parseable as PDF → reject; (2) `is_encrypted` → reject "encrypted/password-protected" + workaround; (3) AcroForm with `/XFA` → reject "XFA (LiveCycle)" + flatten workaround; (4) AcroForm with fields → form kind; (5) text layer present (any page yields non-empty `extract_text()`) → fixed-layout kind; (6) pages with images but no text → reject "scanned/image-only" (OCR out of scope). Cross-misuse signals (FR-023): form kind seen by draft-profile, or ≥3-page repeating record structure seen by draft-template → warn + require `--force`.

**Rationale**: deterministic, cheap (metadata + first-pages text), and every rejection names its condition and workaround per FR-010.

## R8 — Round-trip verification mechanics

**Decision**: `render/pdf_roundtrip.py` — forms: reopen output with pypdf, compare every registered field's value string-exact against the applied record. Fixed-layout: pdfplumber-extract words from the output, for each registered region assert the expected text appears within the region bbox (± 2pt tolerance) and, for image regions, that an image object overlaps the region with the expected source dimensions ratio; content match via the embedded image's XObject data hash equal to the stored extracted-image hash. Verification runs on EVERY render (not only tests) and mismatches raise render failures → exceptions report (FR-013/FR-014). Golden tests additionally freeze extracted (text, x0, y0, x1, y1) tuples for the fixture template (SC-005).

**Rationale**: verification uses the *reading* libraries (pdfplumber/pypdf), not the writing path — an independent check, in the spirit of SafeCard honesty.

## R9 — Determinism of produced PDFs

**Decision**: byte-identical re-runs (FR-015) require pinning PDF metadata: fixed `/Producer`/`/CreationDate`/`/ModDate` (epoch constant), reportlab `invariant=1` mode, stable object ordering via single-pass writes, and content-addressed image inputs. The existing determinism-test pattern (canonicalize.py) extends with a PDF canonical comparison that masks the documented timestamp fields only.

**Rationale**: both libs are deterministic once wall-clock metadata is pinned; this is the same "timestamps excepted" carve-out the constitution already grants.

## R10 — Existing-behaviour regression baseline (SC-007)

**Decision**: before any feature code, capture byte-hashes of current scopito v2020 extraction output and interim template renders on the seed fixtures into `tests/invariants/baselines/`; a regression test asserts equality for the life of the branch.

**Rationale**: SC-007 is only provable against a pre-change baseline; capturing it is therefore the first implementation task after ASSUMPTIONS.md logging.
