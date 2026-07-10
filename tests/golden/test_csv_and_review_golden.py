"""T044 golden: defect CSV and HTML review sheet render byte-identically to
the committed goldens for fixed inputs."""

from pathlib import Path

from rmu.mapping.review_sheet import build_review_html
from rmu.render.csv import render_csv
from tests.golden.make_golden import (
    CSV_COLUMNS,
    CSV_ROWS,
    REVIEW_DOC,
    REVIEW_NORMALIZED,
)

DATA = Path("tests/golden/data")


def test_defect_csv_matches_golden():
    assert render_csv(CSV_ROWS, CSV_COLUMNS) == (DATA / "expected_defects.csv").read_bytes()


def test_review_sheet_matches_golden():
    html = build_review_html(
        1, "ai", "scopito.pdf.powerline@v2020", "interim.defect_csv@1",
        "Distribution-report.pdf", REVIEW_DOC, REVIEW_NORMALIZED,
        ["finding_id", "priority", "defect_code", "inspection_method",
         "contract_number"],
    )
    assert html == (DATA / "expected_review.html").read_text(encoding="utf-8")
