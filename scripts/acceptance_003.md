# SC-001 Acceptance Protocol — feature 003 (Rayno runs this by hand)

The held-out fixture (the Zeitview demo report in `seed/holdout/`) has never
been read by any development or tuning activity — `tests/invariants/
test_quarantine.py` enforces that no code references it. This protocol is its
one legitimate consumer. Run it ONCE, when the feature branch is otherwise
complete.

## Steps

1. **Draft** (first and only automated contact with the fixture):
   `uv run rmu onboard draft-profile seed/holdout/<the-zeitview-file>.pdf`
   - If it is rejected (scanned/encrypted), record that as the acceptance
     outcome and log a new assumption in ASSUMPTIONS.md — do not work around it.
2. **Measure BEFORE any correction** (the SC-001 number):
   - Open the review sheet next to the PDF.
   - Count records the proposal captures correctly (right rows, right columns,
     right values) vs the true record count in the document.
   - **PASS requires >= 80% correct before any human edit.** Record the
     numerator/denominator in STATUS.md.
3. **Validate**: confirm/correct/remove every element in the draft YAML —
   note how many minutes this takes (SC-003 target: < 30 min).
4. **Approve**: `uv run rmu onboard approve <id> --as zeitview.pdf.<jobtype>@v1 --by rayno`
   - Verify-on-approve must pass; if it returns mismatches, that is a FAIL of
     SC-002 — investigate before re-approving.
5. **Confirm 100% of the validated subset**: re-run extraction
   (`uv run rmu extract` on the fixture via the registered profile, or inspect
   the verify report) — every human-validated element must extract exactly.
6. Record in STATUS.md: SC-001 %, SC-003 minutes, pass/fail, date.

## Rules

- Never add this fixture to any test, fixture builder, or tuning loop —
  measuring against it more than once per profile version invalidates SC-001.
- The fixture stays untracked (owner decision 2026-07-12); keep a private copy.
