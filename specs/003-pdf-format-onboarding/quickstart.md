# Quickstart: Onboarding a New PDF Format (003)

End-to-end walkthrough on demo/synthetic data only (Constitution VII). Assumes `uv sync` done and migrations applied (`uv run rmu db upgrade`).

## A. Onboard a new source shape (US1)

```bash
# 1. A structured PDF the tool doesn't recognise (synthetic fixture, NOT the quarantined Zeitview file)
uv run rmu onboard draft-profile tests/fixtures/synthetic_thermal_report.pdf
# → proposal #7, store/drafts/7.yaml, review sheet store/drafts/7.html
#   elements: 3 header fields, 1 record table (6 columns), 1 image region,
#   fingerprint (2 anchors + header regex) — each with confidence + evidence

# 2. Review: open the HTML sheet next to the PDF; edit store/drafts/7.yaml —
#    set each element's review_state to confirmed / corrected (+corrected_payload) / removed
uv run rmu onboard review 7 --regenerate-sheet   # re-check what still blocks approval

# 3. Approve — verify-on-approve re-extracts the exemplar and checks the fingerprint
uv run rmu onboard approve 7 --as synthetic.pdf.thermal@v1
# → registered SourceProfile synthetic.pdf.thermal v1, profiles/synthetic.pdf.thermal.v1.yaml
#   approved_by=<operator>, approved_at recorded

# 4. From now on, same-shape PDFs detect + extract deterministically
uv run rmu extract tests/fixtures/synthetic_thermal_report_2.pdf   # auto-detected, no AI
```

## B. Onboard a PDF target format (US3)

```bash
# Fillable form:
uv run rmu onboard draft-template tests/fixtures/defect_form.pdf
# → kind=pdf_form, fields enumerated with PDF-declared hints (required, kinds, options)

# Fixed-layout:
uv run rmu onboard draft-template tests/fixtures/summary_layout.pdf
# → kind=pdf_overlay, labelled regions with page coordinates (text + image kinds)

# Review + approve (template approval test-renders sample values and round-trips):
uv run rmu onboard approve 8 --name ias.defect_form@1
```

## C. Render a batch into the PDF target (US4)

```bash
uv run rmu apply --batch demo01 --template ias.defect_form@1 ...
# per_record cardinality → one filled PDF per record in the run's output dir;
# round-trip verification runs on every file; failures land in the exceptions report
```

## D. Safety checks to demo (US2)

```bash
# Draft artifacts can never be applied:
uv run rmu apply --batch demo02 --profile <draft-proposal-ref>
# → DraftArtifactError: ... status=draft ... only approved v1+ artifacts can be applied (SC-006)

# Drift still blocks, now with a recovery hint:
uv run rmu apply --batch demo03 ...   # deliberately drifted input
# → SafeCard BLOCK + hint: rmu onboard draft-profile <file> --seed-from synthetic.pdf.thermal@v1
```

## E. Acceptance run (SC-001) — Rayno only

The Zeitview demo report in `seed/source_samples/` is QUARANTINED: no dev command, test, or tuning ever reads it. When the feature is complete, run `draft-profile` against it once, count correct records before corrections (≥80% required), then validate/approve and confirm 100% of the validated subset extracts.
