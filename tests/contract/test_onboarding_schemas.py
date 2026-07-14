"""T006 — contract tests: onboarding schemas accept the canonical shapes and
reject structural violations (Constitution IV: registered artifacts are
schema-validated data)."""

from __future__ import annotations

import pytest

from rmu.onboard.schemas import (
    SchemaValidationError,
    validate_pdf_template,
    validate_proposal,
    validate_recipe,
)

SHA = "a" * 64

RECIPE = {
    "key": "synthetic.pdf.survey",
    "structural_version": "v1",
    "platform": "synthetic",
    "export_kind": "pdf",
    "job_type": "survey",
    "extractor_ref": "rmu.extract.recipe_pdf",
    "effective_from": "2026-07-12",
    "fingerprint": {"required_text": ["Defect register"]},
    "records": {
        "detection": {"mode": "column_clusters",
                      "column_x_ranges": [[40, 100], [110, 200]],
                      "row_pattern": r"^DF-\d{3}$"},
        "columns": [{"name": "ref"}, {"name": "class"}],
    },
}

PROPOSAL = {
    "kind": "profile",
    "exemplars": [SHA],
    "elements": [{
        "id": "hdr-1",
        "element_kind": "header_field",
        "confidence": 0.8,
        "evidence": {"pages": [1], "source": "heuristic"},
        "review_state": "proposed",
        "payload": {"name": "survey_date", "labels": ["Survey date:"]},
    }],
}

FORM_TEMPLATE = {
    "kind": "pdf_form",
    "pdf_object": SHA,
    "cardinality": "per_record",
    "fields": [{"field_id": "asset_id", "target_field": "asset_name", "kind": "text"}],
}

OVERLAY_TEMPLATE = {
    "kind": "pdf_overlay",
    "pdf_object": SHA,
    "cardinality": "per_record",
    "regions": [{"label": "Asset ID:", "target_field": "asset_name", "kind": "text",
                 "page": 1, "bbox": [150, 746, 370, 762]}],
}


def test_canonical_documents_validate():
    validate_recipe(RECIPE)
    validate_proposal(PROPOSAL)
    validate_pdf_template(FORM_TEMPLATE)
    validate_pdf_template(OVERLAY_TEMPLATE)


def test_recipe_rejects_non_generic_extractor():
    bad = {**RECIPE, "extractor_ref": "rmu.extract.custom_generated_code"}
    with pytest.raises(SchemaValidationError):
        validate_recipe(bad)  # onboarded profiles are data for ONE generic engine


def test_recipe_requires_fingerprint():
    bad = {k: v for k, v in RECIPE.items() if k != "fingerprint"}
    with pytest.raises(SchemaValidationError):
        validate_recipe(bad)  # FR-024: no profile without a detection fingerprint


def test_proposal_rejects_unknown_review_state():
    bad = {**PROPOSAL, "elements": [{**PROPOSAL["elements"][0], "review_state": "maybe"}]}
    with pytest.raises(SchemaValidationError):
        validate_proposal(bad)


def test_proposal_confidence_bounded():
    bad = {**PROPOSAL, "elements": [{**PROPOSAL["elements"][0], "confidence": 1.5}]}
    with pytest.raises(SchemaValidationError):
        validate_proposal(bad)


def test_form_template_requires_fields_and_overlay_requires_regions():
    with pytest.raises(SchemaValidationError):
        validate_pdf_template({k: v for k, v in FORM_TEMPLATE.items() if k != "fields"})
    with pytest.raises(SchemaValidationError):
        validate_pdf_template({k: v for k, v in OVERLAY_TEMPLATE.items() if k != "regions"})


def test_template_cardinality_is_closed_enum():
    bad = {**FORM_TEMPLATE, "cardinality": "per_page"}
    with pytest.raises(SchemaValidationError):
        validate_pdf_template(bad)
