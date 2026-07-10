# Transform YAML Contract (v1 schema)

Validated by `src/rmu/mapping/schemas/transform-v1.json` (jsonschema). Transforms are
data (Constitution IV); anything outside this contract is rejected at load.

```yaml
meta:
  source_profile: scopito.pdf.powerline@v2020     # key@structural_version
  target_template: interim.defect_csv@1           # name@version — pinned
  version: 1
  parent_version: null

routes:                       # target_field -> source route
  asset_id:
    from: header.inspection_name
    tier: T1                  # T0|T1 only in an approved transform
  priority:
    from: finding.severity
    value_map: {name: severity_to_priority, version: 1}   # version REQUIRED
  defect_code:
    from: finding.issues
    value_map: {name: issue_to_defect_code, version: 1}

constants:                    # target_field -> literal
  inspection_method: "UAV visual"

formulas:                     # closed set only (research R5, spec FR-007)
  report_ref:
    fn: concat
    args: [{field: header.company}, {lit: "-"}, {field: header.report_date}]
  inspection_date:
    fn: date_format
    args: [{field: header.report_date}, {lit: "%Y-%m-%d"}]

prompts:                      # answered at batch launch, recorded on the ApplyRun
  - {key: contract_number, label: "Client contract number", required: true}

exceptions:                   # OOV policy is fixed: exception, never guess
  unmapped_optional: skip     # only optional fields may be skipped
```

## Validation rules enforced by schema + loader

1. `fn` ∈ {concat, substring, regex_extract, date_format, number_format, arith};
   args reference `field`, `lit`, or `prompt` only. No other function survives
   validation (Constitution II, IV).
2. Every `value_map` reference carries an explicit `version` and must resolve to an
   existing ValueMap row at approval time.
3. Every required target field of the pinned template version appears in exactly one
   of `routes` / `constants` / `formulas` / `prompts` — else approval fails (FR-007).
4. `tier` values `T2`/`T3` fail approval validation (design §7).
5. No `now()`, no environment reads, no randomness — not representable in the grammar.
```
