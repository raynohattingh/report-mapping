"""T032 — SC-009 performance smoke: draft-profile analysis of a ~300-page
report completes in under 10 minutes locally (heuristics path; enrichment is
page-sampled by design and adds bounded work). Marked slow."""

from __future__ import annotations

import random
import time

import pytest

from rmu.onboard.analyze_source import analyze
from tests.fixtures.make_fixtures import _survey_rows, build_survey

#: ~27 rows/page in the fixture layout -> ~300 pages
BIG_ROWS = 8100
BUDGET_SECONDS = 600  # SC-009


@pytest.mark.slow
def test_300_page_analysis_within_budget(tmp_path):
    rng = random.Random(20260713)
    big = tmp_path / "big_survey.pdf"
    rows = _survey_rows(rng, BIG_ROWS)
    for i, row in enumerate(rows, start=1):
        row["ref"] = f"DF-{i:05d}"  # fixed width: one structure class end-to-end
    build_survey(big, "Perf smoke survey", rows)

    import pdfplumber

    with pdfplumber.open(big) as pdf:
        pages = len(pdf.pages)
    assert pages >= 280, f"fixture too small for the smoke ({pages} pages)"

    started = time.monotonic()
    document = analyze([big])
    elapsed = time.monotonic() - started

    table = next(e for e in document["elements"] if e["element_kind"] == "record_table")
    assert table["evidence"]["recurrence"] == BIG_ROWS  # nothing dropped
    assert elapsed < BUDGET_SECONDS, f"analysis took {elapsed:.0f}s (SC-009 budget 600s)"
