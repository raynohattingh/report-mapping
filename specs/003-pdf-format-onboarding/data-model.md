# Data Model: PDF Format Onboarding (003)

Extends `specs/001-report-mapping-v1/data-model.md`. All changes are **additive** (Constitution III): one new table, zero changes to existing columns, no migrations touching ★ registry rows.

## New table: `onboarding_proposals`

Mirrors the `mapping_sessions` draft pattern — NOT an append-only registry table; drafts are working state, registries are truth.

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| kind | str(10) | `profile` \| `template` |
| status | str(12) | `draft` \| `approved` \| `abandoned` (default `draft`) |
| exemplar_shas | JSON list | sha256 of exemplar PDF(s) (1..n for profiles, exactly 1 for templates) |
| seeded_from_profile_id | int FK source_profiles, nullable | set when created via drift re-onboarding (FR-021) |
| elements | JSON | full proposal document (see contracts/proposal.schema.json): elements each carry `id, kind, evidence, confidence, review_state (proposed\|confirmed\|corrected\|removed), corrected_value?` |
| diagnosis | JSON, nullable | analysis diagnosis (what was searched/found) — always present for skeleton proposals (FR-001b) |
| draft_ref | str(64), nullable | store/drafts YAML object hash while editable |
| ai_assist | JSON, nullable | 002-layer provenance: {mode, client, sampled_pages, enrichments} — NULL when `--no-ai` |
| created_at | datetime | |
| approved_by | str(80), nullable | operator identity at approval (FR-017) |
| approved_at | datetime, nullable | |
| verify_report | JSON, nullable | verify-on-approve results incl. fingerprint collision check (FR-022/FR-024); persisted on failure too (returned-to-review evidence) |
| resulting_profile_id | int FK source_profiles, nullable | set on kind=profile approval |
| resulting_template_id | int FK target_templates, nullable | set on kind=template approval |

**State transitions**: `draft → approved` (only via verify-on-approve success), `draft → abandoned` (explicit discard; no effect anywhere), `draft → draft` (verify failure returns with `verify_report` populated). No transition out of `approved`/`abandoned`.

## Existing tables — used as-is (no schema change)

### SourceProfile (registered onboarded profile)

New rows only. Onboarded rows use the existing columns:
- `key` — analyst-chosen, e.g. `zeitview.pdf.roofthermal`; `structural_version` e.g. `v2026`
- `fingerprint` — same dict schema Detect already matches (`required_text`, `table_header_regex`), extended keys allowed (`page_anatomy`) and ignored by older matchers
- `extractor_ref` — always `rmu.extract.recipe_pdf` for onboarded profiles
- recipe body lives in `profiles/<key>.<version>.yaml` (schema: contracts/recipe.schema.json), exactly like scopito's anchors today

Provenance (who/when/from which proposal) is queryable through `onboarding_proposals.resulting_profile_id` — no registry column needed.

### TargetTemplate (registered onboarded PDF template)

New rows only. Onboarded rows use existing JSON columns:
- `template_files` — `{kind: "pdf_form" | "pdf_overlay", pdf_object: <store sha>, cardinality: "per_record" | "per_batch", fields|regions: [...] }` per contracts/pdf-template.schema.json
- `required_schema` — required target fields (from PDF hints + analyst edits, FR-025)
- `validation_rules` — formats, vocab references (seed tables by name, loaded as data)
- `interim` — `false` for onboarded client formats

### ApplyRun / ConversionException

Unchanged. New exception kinds emitted by this feature reuse the existing `kind` column values plus two new values: `draft_artifact` (FR-016 pre-flight) and `render_roundtrip` (FR-013 failures). `outputs_manifest.output_kind` gains `pdf_form` / `pdf_overlay`.

## Store layout additions

```
store/objects/   + template source PDFs (content-addressed, referenced by template_files.pdf_object)
                 + extracted record images (content-addressed; recipe extraction output references them)
store/drafts/    + onboarding proposal YAML while status=draft (draft_ref)
profiles/        + <key>.<structural_version>.yaml recipe files for onboarded profiles
```

## Validation rules (from FRs)

- Proposal element `review_state` must be non-`proposed` for ALL elements before approval is accepted (FR-003).
- `kind=profile` approval: re-extraction on every exemplar must equal confirmed/corrected elements exactly; fingerprint must match all exemplars and match NO existing active profile (FR-022, FR-024).
- `kind=template` approval: test render with sample values must pass round-trip (FR-022).
- Recipe YAML and template config are jsonschema-validated before registration (Constitution IV).
- `onboarding_proposals` is NOT in `APPEND_ONLY_MODELS` (drafts mutate); the rows it *produces* are.

## Alembic migration

One additive migration: `create_table onboarding_proposals`. No existing table touched. Reviewed before apply ([REVIEW] gate).
