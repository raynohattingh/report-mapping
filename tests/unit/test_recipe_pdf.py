"""T012 — generic recipe-driven extraction (research R5, FR-004/FR-001a).

One engine, recipe as data: onboarded profiles never get per-profile code."""

from __future__ import annotations

from pathlib import Path

import pytest

from rmu.extract.recipe_pdf import extract
from rmu.onboard.schemas import validate_recipe

FIX = Path("tests/fixtures/onboarding")

RECIPE = {
    "key": "synthetic.pdf.survey",
    "structural_version": "v1",
    "platform": "synthetic",
    "export_kind": "pdf",
    "job_type": "survey",
    "extractor_ref": "rmu.extract.recipe_pdf",
    "effective_from": "2026-07-12",
    "fingerprint": {
        "required_text": ["Defect register", "Survey date:"],
        "table_header_regex": r"^Ref\s+Class\s+Component\s+Observation\s+Sheet$",
    },
    "header_fields": [
        {"name": "survey_date", "strategy": "label_right", "labels": ["Survey date:"]},
        {"name": "client", "strategy": "label_right", "labels": ["Client:"]},
        {"name": "site", "strategy": "label_right", "labels": ["Site:"]},
        {"name": "defects_recorded", "strategy": "label_right",
         "labels": ["Defects recorded:"]},
    ],
    "records": {
        "detection": {
            "mode": "column_clusters",
            "column_x_ranges": [[38, 105], [108, 205], [208, 315], [318, 515], [518, 556]],
            "row_pattern": r"^DF-\d{3}$",
            "table_header_regex": r"^Ref\s+Class\s+Component\s+Observation\s+Sheet$",
        },
        "columns": [{"name": "ref"}, {"name": "class"}, {"name": "component"},
                    {"name": "observation"}, {"name": "sheet"}],
        "continuation": {"mode": "repeat_header"},
    },
    "images": [{"name": "photo", "association": "row_y_overlap"}],
    "furniture": ["FieldSurvey Pro export", "Confidential - page"],
}


@pytest.fixture(autouse=True)
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))


def test_recipe_is_schema_valid():
    validate_recipe(RECIPE)


def test_extracts_all_records_with_correct_columns():
    n = extract(FIX / "survey_report_a.pdf", RECIPE)
    assert n["schema"] == "rmu.normalized/1"
    assert n["profile"] == "synthetic.pdf.survey@v1"
    assert len(n["findings"]) == 26
    first = n["findings"][0]
    assert first["ref"] == "DF-001"
    assert first["class"] in {"Structural", "Electrical", "Vegetation", "Corrosion"}
    assert first["observation"]  # multi-word cell joined
    assert n["findings"][-1]["ref"] == "DF-026"  # continuation across the page break
    assert n["header"]["survey_date"] == "03 Jul 2026"
    assert n["header"]["client"] == "Synthetic Utility Co"
    assert n["integrity"]["anchors_missing"] == []


def test_images_extracted_per_record():
    n = extract(FIX / "survey_report_a.pdf", RECIPE)
    refs = [f.get("photo_ref") for f in n["findings"]]
    assert all(refs), "every record row has a thumbnail in the fixture (FR-001a)"
    assert len(set(refs)) == len(refs)  # distinct images -> distinct content hashes


def test_furniture_never_becomes_a_record():
    n = extract(FIX / "survey_report_a.pdf", RECIPE)
    texts = {f["ref"] for f in n["findings"]}
    assert not any("Confidential" in t or "FieldSurvey" in t for t in texts)


def test_fingerprint_mismatch_reports_missing_anchor():
    n = extract(FIX / "survey_report_drifted.pdf", RECIPE)  # Class renamed Category
    assert n["integrity"]["anchors_missing"]  # -> drift-BLOCK upstream of Apply
