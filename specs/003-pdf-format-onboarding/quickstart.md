# Quickstart: Onboarding a New PDF Format (003)

End-to-end walkthrough on demo/synthetic data only (Constitution VII). Assumes `uv sync` done and migrations applied (`uv run rmu db init && uv run rmu seed load`).

## A. Onboard a new source shape (US1)

```bash
# 1. A structured PDF the tool doesn't recognise (synthetic fixture, NOT the quarantined Zeitview file)
uv run rmu onboard draft-profile tests/fixtures/onboarding/survey_report_a.pdf
# → proposal #7, store/drafts/7.yaml, review sheet store/drafts/7.html
#   elements: 3 header fields, 1 record table (6 columns), 1 image region,
#   fingerprint (2 anchors + header regex) — each with confidence + evidence

# 2. Review: open the HTML sheet next to the PDF; edit store/drafts/7.yaml —
#    set each element's review_state to confirmed / corrected (+corrected_payload) / removed
uv run rmu onboard review 7 --regenerate-sheet   # re-check what still blocks approval

# 3. Approve — verify-on-approve re-extracts the exemplar and checks the fingerprint
uv run rmu onboard approve 7 --as synthetic.pdf.survey@v1 --by rayno
# → registered SourceProfile synthetic.pdf.survey v1, profiles/synthetic.pdf.survey.v1.yaml
#   approved_by=<operator>, approved_at recorded

# 4. From now on, same-shape PDFs auto-detect and convert deterministically
uv run rmu profile suggest tests/fixtures/onboarding/survey_report_b.pdf  # detected, no AI
```

## B. Onboard a PDF target format (US3)

```bash
# Fillable form:
uv run rmu onboard draft-template tests/fixtures/onboarding/target_form.pdf
# → kind=pdf_form, fields enumerated with PDF-declared hints (required, kinds, options)

# Fixed-layout:
uv run rmu onboard draft-template tests/fixtures/onboarding/target_fixed.pdf
# → kind=pdf_overlay, labelled regions with page coordinates (text + image kinds)

# Review + approve (template approval test-renders sample values and round-trips):
uv run rmu onboard approve 8 --name ias.defect_form@1 --by rayno
```

## C. Render a batch into the PDF target (US4)

```bash
uv run rmu apply run ./batch_folder \
    --transform synthetic.pdf.survey@v1:ias.defect_form@1
# per_record cardinality → one filled PDF per record in the run's output dir;
# round-trip verification runs on every file; failures land in the exceptions report
```

## D. Safety checks to demo (US2)

```bash
# Draft artifacts can never be applied (ref not yet approved/registered):
uv run rmu apply run ./batch_folder --transform notyet.pdf.survey@v1:interim.defect_csv@1
# → error: ... proposal #N exist with status=draft ... only human-approved v1+ artifacts (SC-006)

# Drift still blocks, now with a recovery hint in exceptions.csv:
uv run rmu apply run ./batch_with_drifted_pdf --transform synthetic.pdf.survey@v1:interim.defect_csv@1
# → blocked; suggestion: rmu onboard draft-profile <file> --seed-from synthetic.pdf.survey@v1
```

## E. Acceptance run (SC-001) — Rayno only

The Zeitview demo report in `seed/holdout/` is QUARANTINED (untracked, owner decision): no dev command, test, or tuning ever reads it. Follow scripts/acceptance_003.md exactly: one draft-profile run, count correct records before corrections (≥80% required), validate/approve, confirm 100% of the validated subset.
