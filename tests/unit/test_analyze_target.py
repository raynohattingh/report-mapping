"""T023 — target analysis (FR-007/FR-008/FR-025): the PDF's own declarations
arrive as pdf_declared evidence; fixed layouts yield coordinate regions."""

from __future__ import annotations

from pathlib import Path

from rmu.onboard.analyze_target import analyze

FIX = Path("tests/fixtures/onboarding")


def _by_kind(doc, kind):
    return [e for e in doc["elements"] if e["element_kind"] == kind]


def test_form_fields_enumerated_with_pdf_declared_hints():
    doc = analyze(FIX / "target_form.pdf", kind="form")
    fields = {e["payload"]["field_id"]: e for e in _by_kind(doc, "form_field")}

    assert set(fields) == {"asset_id", "defect_code", "priority", "comments", "reinspect"}
    assert fields["asset_id"]["payload"]["required"] is True  # PDF-declared (FR-025)
    assert fields["comments"]["payload"]["required"] is False  # multiline, not required
    assert fields["priority"]["payload"]["kind"] == "choice"
    assert set(fields["priority"]["payload"]["options"]) == {"P1", "P2", "P3", "P4"}
    assert fields["reinspect"]["payload"]["kind"] == "checkbox"
    for e in fields.values():
        assert e["evidence"]["source"] == "pdf_declared"
        assert e["review_state"] == "proposed"  # nothing registers unreviewed


def test_fixed_layout_regions_with_coordinates():
    doc = analyze(FIX / "target_fixed.pdf", kind="fixed_layout")
    regions = {e["payload"]["label"]: e for e in _by_kind(doc, "overlay_region")}

    assert {"Asset ID:", "Defect code:", "Priority:", "Photo:"} <= set(regions)
    asset = regions["Asset ID:"]["payload"]
    assert asset["kind"] == "text" and asset["page"] == 1
    x0, y0, x1, y1 = asset["bbox"]
    assert x0 > 140 and x1 > x0 and y1 > y0  # the box right of the label

    photo = regions["Photo:"]["payload"]
    assert photo["kind"] == "image"  # tall box -> image region
    px0, py0, px1, py1 = photo["bbox"]
    assert (px1 - px0) > 100 and (py1 - py0) > 100


def test_cardinality_is_a_reviewable_element():
    doc = analyze(FIX / "target_form.pdf", kind="form")
    card = _by_kind(doc, "cardinality")
    assert len(card) == 1
    assert card[0]["payload"]["cardinality"] == "per_record"
    assert card[0]["review_state"] == "proposed"
