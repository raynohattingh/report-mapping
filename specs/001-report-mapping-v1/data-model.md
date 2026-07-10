# Data Model — Report-Mapping Utility v1 (Weekend Slice)

SQLAlchemy models on SQLite (Postgres-ready by config). ★ = versioned, append-only,
effective-dated (Constitution III; enforcement per research R2). Blobs live in the
content-addressed `store/` (R3); tables hold hashes + metadata.

## SourceProfile ★

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| key | str | e.g. `scopito.pdf.powerline` |
| structural_version | str | e.g. `v2020` (A1) |
| platform / export_kind / job_type | str | `scopito` / `pdf` / `powerline` |
| fingerprint | JSON | detection anchors: page-1 labels, table header row, section titles |
| extractor_ref | str | dotted path of the per-profile parser |
| declared_totals_fields | JSON | which header fields carry counts for the FR-016 cross-check |
| status | enum | `active` \| `superseded` |
| effective_from | date | |

**Unique**: (key, structural_version).

## TargetTemplate ★

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| institution | str | `INTERIM` this slice (Constitution I) |
| name | str | `interim.annexc_pack` \| `interim.defect_csv` |
| version | int | |
| effective_from | date | |
| template_files | JSON | store hashes of docx/xlsx/csv template blobs |
| required_schema | JSON | required target fields + types |
| validation_rules | JSON | vocabulary + cross-field checks |
| interim | bool | MUST be true for both shipped templates (SC-008) |

**Unique**: (name, version).

## Transform ★

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| source_profile_id | FK | |
| target_template_id | FK | pins template version by row identity |
| version | int | |
| effective_from | date | |
| yaml_body | text | schema-validated (R5); value-map refs pinned `{name, version}` |
| approved_by / approved_at | str / datetime | approval metadata (FR-009) |
| parent_version | int nullable | lineage |

**Unique**: (source_profile_id, target_template_id, version).
**Rule**: yaml_body must validate against transform-v1 schema at insert; every
value-map ref must resolve to an existing (name, version) row.

## ValueMap ★

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| name | str | e.g. `severity_to_priority`, `issue_to_defect_code` |
| version | int | |
| entries | JSON | `[{source_value, target_value, provenance: human\|ai-accepted, note}]` |
| effective_from | date | |

**Unique**: (name, version). Growth = new version + new Transform version pointing
to it (spec FR-019).

## MappingSession

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| source_profile_id / target_template_id | FK | |
| exemplar_document_id | FK SourceDocument | |
| mode | enum | `ai` \| `manual` (FR-010) |
| proposals | JSON | every AI proposal: route, tier, rationale, timestamp (FR-005, FR-021) |
| decisions | JSON | every human accept/edit/reject + fills, timestamps (FR-021) |
| status | enum | `draft` → `approved` \| `abandoned` |
| resulting_transform_id | FK nullable | set on approval |

**Transition**: `draft → approved` allowed only when zero unmapped required fields
and zero unreviewed proposals remain (FR-007).

## SourceDocument

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| sha256 | str unique | content fingerprint; duplicate detection (edge case) |
| original_filename | str | |
| profile_id | FK nullable | null = unrecognized → quarantine |
| received_at | datetime | audit only, never in outputs |
| extraction_ref | str nullable | store hash of NormalizedRecords JSON |

## ApplyRun ★

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| batch_label | str | |
| document_shas | JSON | ordered input fingerprints |
| prompt_answers | JSON | per-batch answers, replayed on regen (FR-017) |
| transform_id | FK | fixes transform version → value-map versions transitively |
| target_template_id | FK | fixes template version |
| safecard | JSON | per-document verdicts + batch summary (R10) |
| outputs_manifest | JSON | `[{document_sha, output_kind, store_hash}]` |
| exceptions_report_ref | str | store hash; ALWAYS present (FR-013) |
| completed_at | datetime | written only on successful completion (interrupted-run edge case) |

**Rule**: a row exists only for completed runs; regeneration reads this row and must
reproduce every `store_hash` in `outputs_manifest` exactly (FR-018).

## Exception

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| apply_run_id | FK | |
| document_sha | str | |
| record_ref | str nullable | null for document-level (quarantine) entries |
| kind | enum | `oov_value` \| `record_parse` \| `drift_block` \| `unknown_profile` \| `duplicate` |
| detail | JSON | failing value, reason, suggested resolution (FR-012) |
| status | enum | `open` → `resolved` |
| resolution | JSON nullable | incl. value-map delta ref if any |

## NormalizedRecords (artifact, not a table)

Per-profile extraction product stored as JSON in `store/` (design §5 — no universal
schema): `ReportHeader` (inspection name, report date, type, company, declared
counts) + `FindingRecord[]` (id, severity `1-5|?` per A3, user_tags, issues,
comments, page) + assets manifest. Shared core only; no ontology.

## Confidence tiers (SafeCard, design §7)

`T0 deterministic` / `T1 validated` / `T2 proposed` (never in an approved transform)
/ `T3 unmapped`. Worst tier of any required field gates the document verdict.
