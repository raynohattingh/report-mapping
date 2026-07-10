"""Regenerate the committed golden files from FIXED inputs.

Run only when a rendering change is intended; the diff is the review artifact:
    uv run python tests/golden/make_golden.py
"""

from __future__ import annotations

from pathlib import Path

from rmu.mapping.review_sheet import build_review_html
from rmu.render.csv import render_csv
from rmu.render.docx import render_pack

DATA = Path(__file__).parent / "data"

PACK_CONTEXT = {
    "inspection_name": "Golden inspection",
    "inspection_date": "2026-07-11",
    "contract_number": "GOLD-1",
    "inspection_method": "UAV visual",
    "company": "Synthetic Ops",
    "findings": [
        {"finding_id": "9000001", "defect_code": "C1", "priority": "P1",
         "source_severity": "5", "comments": "burned lead"},
        {"finding_id": "9000002", "defect_code": "F12", "priority": "POI",
         "source_severity": "?", "comments": ""},
    ],
}

CSV_ROWS = [
    {"finding_id": "9000001", "asset_name": "Golden inspection",
     "inspection_date": "2026-07-11", "defect_code": "C1", "priority": "P1",
     "source_severity": "5", "contract_number": "GOLD-1",
     "inspection_method": "UAV visual", "user_tags": "SYN-1 | RGB",
     "comments": "burned lead", "source_page": "2"},
]
CSV_COLUMNS = ["finding_id", "asset_name", "inspection_date", "defect_code",
               "priority", "source_severity", "contract_number",
               "inspection_method", "user_tags", "comments", "source_page"]

REVIEW_DOC = {
    "routes": {
        "finding_id": {"from": "finding.id", "tier": "T0"},
        "priority": {"from": "finding.severity", "tier": "T2",
                     "rationale": "severity converts to priority",
                     "value_map": {"name": "severity_to_priority", "version": 1}},
        "defect_code": {"from": "finding.issues", "tier": "T3",
                        "rationale": "unmapped"},
    },
    "constants": {"inspection_method": "UAV visual"},
    "formulas": {},
    "prompts": [{"key": "contract_number", "label": "Client contract number",
                 "required": True}],
}
REVIEW_NORMALIZED = {
    "header": {"inspection_name": "Golden inspection", "report_date": "Jul 5, 2026"},
    "findings": [{"id": "9000001", "severity": "5", "user_tags": ["SYN-1"],
                  "issues": ["Conductor Damage"], "comments": "burned lead",
                  "page": 2}],
}


def main() -> None:
    DATA.mkdir(exist_ok=True)
    template_bytes = Path("templates/interim.annexc_pack/pack_template.docx").read_bytes()
    (DATA / "expected_pack.docx").write_bytes(render_pack(template_bytes, PACK_CONTEXT))
    (DATA / "expected_defects.csv").write_bytes(render_csv(CSV_ROWS, CSV_COLUMNS))
    (DATA / "expected_review.html").write_text(
        build_review_html(
            1, "ai", "scopito.pdf.powerline@v2020", "interim.defect_csv@1",
            "Distribution-report.pdf", REVIEW_DOC, REVIEW_NORMALIZED,
            ["finding_id", "priority", "defect_code", "inspection_method",
             "contract_number"],
        ),
        encoding="utf-8",
    )
    print(f"golden files written to {DATA}")


if __name__ == "__main__":
    main()
