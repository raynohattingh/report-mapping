# Quickstart — Report-Mapping Utility v1

```bash
# Setup (once)
uv sync                                   # Python 3.12, all deps incl. dev
uv run rmu db init                        # Alembic schema
uv run rmu seed load                      # defect codes, interim templates, scopito profile

# One-time mapping session (US1) — manual path (works with zero API keys)
uv run rmu map start \
  --profile scopito.pdf.powerline@v2020 \
  --template interim.defect_csv@1 \
  --exemplar seed/source_samples/Distribution-report.pdf \
  --no-ai
# → edit the emitted draft YAML; regenerate the review sheet as you go
uv run rmu map review  --session 1        # HTML review sheet
uv run rmu map preview --session 1        # rendered exemplar in target format
uv run rmu map approve --session 1 --by rayno   # stores Transform v1

# AI-assisted variant: drop --no-ai (requires ANTHROPIC_API_KEY; demo data only, A6)

# Batch conversion (US2) — deterministic, non-interactive
uv run rmu apply run tests/fixtures/batch_20 \
  --transform "scopito.pdf.powerline@v2020:interim.defect_csv@1" \
  --answer contract_number=DEMO-001
# → store/runs/<id>/: per-report outputs + defects.csv + exceptions.csv + safecard.json

# Trust drill (US3)
uv run rmu apply regen <run-id>           # byte-exact regeneration, hash-verified
uv run pytest                             # incl. determinism, append-only, drift-block,
                                          # exceptions-report invariant tests (never cut, D3)
```

Drift drill: `tests/fixtures/drifted/` contains a renamed-header fixture and a
declared-vs-extracted mismatch fixture; both must be BLOCKED and quarantined while
the healthy batch converts (SC-003).
