# CLI Contract — `rmu` (Typer)

All commands are non-interactive except `map review` prompts in manual flow (which
read from a TTY only during the HIL session, never during apply). Exit codes:
`0` success, `1` usage/validation error, `2` blocked (SafeCard/drift), `3` incomplete
approval preconditions.

## Registries (P1)

| Command | Contract |
|---|---|
| `rmu db init` | Create/upgrade schema (Alembic), idempotent. |
| `rmu seed load` | Load defect codes, interim templates, scopito profile from `seed/` + `profiles/` + `templates/`, idempotent. |
| `rmu profile list` / `rmu template list` / `rmu valuemap list` | Tabular listing incl. versions and effective dates. |

## Mapping session (P3)

| Command | Contract |
|---|---|
| `rmu map start --profile scopito.pdf.powerline@v2020 --template interim.defect_csv@1 --exemplar <pdf> [--no-ai]` | Extracts exemplar, emits draft transform YAML + review-sheet HTML paths. With `--no-ai`: draft contains routes/constants skeleton + unmapped list, zero proposals. Without: proposals with tier+rationale from provider (R6). |
| `rmu map review --session <id>` | Regenerates the HTML review sheet from current draft YAML (side-by-side exemplar values, proposals, rationale, decision state). |
| `rmu map preview --session <id>` | Renders the exemplar through the current draft to target format for inspection (FR-008). |
| `rmu map approve --session <id> --by <name>` | Validates: schema-valid YAML, no unmapped required fields, no unreviewed proposals (exit 3 otherwise). Stores Transform vN, pins value-map versions, records session lineage. |

## Batch apply (P4)

| Command | Contract |
|---|---|
| `rmu apply run <folder> --transform <profile+template@ver> [--answer key=value ...] [--label <s>]` | Fails fast (exit 1) listing missing prompt keys. Detects/extracts each PDF; quarantines unknown/drifted docs (exceptions, no output); converts healthy docs; writes outputs + per-report defect CSV + exceptions report (ALWAYS) + SafeCard; records ApplyRun on completion only. Exit 2 if every document blocked. Deterministic: no network, no AI imports on this path. |
| `rmu apply regen <run-id> [--out <dir>]` | Reproduces outputs from the ApplyRun record (inputs by fingerprint from store, recorded prompt answers, pinned versions). Verifies each regenerated file hash equals the manifest hash; nonzero exit on mismatch. Never re-asks prompts. |
| `rmu runs list` / `rmu runs show <run-id>` | Audit inspection: fingerprints, versions, verdicts, exceptions. |

## Output layout per run

```
store/runs/<run-id>/
├── <report-stem>.pack.docx        # interim.annexc_pack output, canonicalized (R1)
├── <report-stem>.defects.csv      # per-report defect CSV (clarify decision 2)
├── exceptions.csv                 # always present (FR-013)
└── safecard.json                  # per-document verdicts + batch summary
```
