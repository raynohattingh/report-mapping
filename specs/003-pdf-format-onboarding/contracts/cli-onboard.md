# CLI Contract: `rmu onboard` sub-app

All commands are local-only; no document content leaves the machine (FR-020). Exit code 0 = success, 1 = user-actionable rejection (with diagnosis), 2 = internal error.

## `rmu onboard draft-profile EXEMPLAR.pdf [EXTRA2.pdf ...] [--no-ai] [--seed-from KEY@VERSION] [--force]`

Analyse an unrecognised source PDF and create a draft profile proposal.

- Multiple exemplars → cross-check; non-generalising elements down-scored + flagged (FR-001).
- `--no-ai` → heuristics-only proposal (FR-020). Default: heuristics + 002 local enrichment when configured.
- `--seed-from` → drift re-onboarding: proposal pre-populated from the existing profile, elements marked as delta (FR-021).
- `--force` → proceed despite document-kind warning (looks like a form/target) (FR-023).
- No structure found → diagnosis + empty skeleton proposal, exit 0 (FR-001b).
- Scanned/encrypted/unparseable → named rejection, exit 1 (FR-010 ladder).
- **Output**: proposal id + `store/drafts/<id>.yaml` + HTML review sheet path. Status: `draft`.

## `rmu onboard draft-template TARGET.pdf [--no-ai] [--force]`

Analyse a target-format PDF and create a draft template proposal.

- AcroForm fields present → form-field schema proposal (kind pdf_form) incl. PDF-declared hints (required flags, kinds, options, max lengths) as `pdf_declared` elements (FR-007, FR-025).
- No fields, text layer present → overlay-region proposal (kind pdf_overlay) with page coordinates (FR-008); region kinds text|image.
- Encrypted / XFA / scanned → named rejection + workaround, exit 1 (FR-010).
- `--force` → proceed despite looks-like-a-source warning (FR-023).
- **Output**: proposal id + draft YAML + HTML review sheet. Status: `draft`.

## `rmu onboard review PROPOSAL_ID [--regenerate-sheet]`

Print proposal status: elements by review_state, low-confidence/non-generalising flags, what blocks approval. `--regenerate-sheet` rebuilds the HTML review sheet after the analyst edits the draft YAML.

## `rmu onboard approve PROPOSAL_ID [--as KEY@VERSION | --name NAME@N]`

Verify-on-approve then register (FR-022):

1. Reject if any element still `proposed` (FR-003) → exit 1 listing unresolved ids.
2. kind=profile: re-run deterministic extraction on all exemplars with the corrected recipe; require exact match with confirmed/corrected elements. Check fingerprint matches all exemplars AND collides with no active registered profile (FR-024).
3. kind=template: test render with sample values; require round-trip pass (FR-013).
4. On failure: proposal stays `draft`, `verify_report` persisted, mismatches printed → exit 1.
5. On success: append registry row (+ `profiles/<key>.<version>.yaml` for profiles), record approved_by (operator identity) / approved_at (FR-017), print registered artifact reference.

## `rmu onboard abandon PROPOSAL_ID`

Mark draft `abandoned`. No effect on any conversion (edge case: abandoned drafts).

## Existing command changes (guard + render only)

- `rmu apply ...` — pre-flight: any artifact reference that does not resolve to a REGISTERED registry row fails with `DraftArtifactError: <ref> is status=draft (proposal #id); only approved v1+ artifacts can be applied` before any record is read (FR-016, SC-006). Emits exception kind `draft_artifact`.
- `rmu render` path — templates with `template_files.kind` `pdf_form`/`pdf_overlay` route to the new renderers; round-trip verification runs on every render; failures emit exception kind `render_roundtrip` (FR-013/FR-014).
- SafeCard BLOCK verdict output gains: `hint: run 'rmu onboard draft-profile <file> --seed-from <key>@<version>'` (FR-021).
