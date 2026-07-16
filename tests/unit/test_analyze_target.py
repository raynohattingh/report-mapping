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


def test_grid_form_proposes_blank_cells_as_regions():
    """A line-drawn grid (no area rects) must yield one region per blank,
    size-valid cell — not an empty skeleton (Eskom-checklist regression).
    Feature 005: qualifying grids reconstruct as a matrix (axis-derived
    `row__col` names); the non-qualifying 2x2 grid B must STILL emit its
    cells flat — no table's cells may silently vanish."""
    doc = analyze(FIX / "target_grid.pdf", kind="fixed_layout")
    regions = _by_kind(doc, "overlay_region")
    fields = {r["payload"]["target_field"] for r in regions}
    # Grid A reconstructs as a matrix: one axis pair + criterion x column cells
    assert len(_by_kind(doc, "row_axis")) == 1
    assert len(_by_kind(doc, "col_axis")) == 1
    assert {"corrosion__result", "corrosion__notes",
            "paint__result", "paint__notes"} <= fields
    assert {"row_3__result", "row_3__notes"} <= fields  # blank criterion row
    # Grid B (2x2, too small for axes): fully blank -> flat positional names
    assert {"cell_p1_r0_c0", "cell_p1_r0_c1", "cell_p1_r1_c0", "cell_p1_r1_c1"} <= fields
    assert len(regions) == 10  # 6 matrix cells + 4 flat; sliver column filtered
    for r in regions:
        assert r["payload"]["kind"] == "text"
        assert r["payload"]["page"] == 1
        assert r["payload"]["label"]  # human-readable name for review/approve
        assert len(r["payload"]["bbox"]) == 4
        assert r["confidence"] == 0.6
        assert r["review_state"] == "proposed"
    # flat cells keep the association provenance of the old grid path
    flat = [r for r in regions if "row_id" not in r["payload"]]
    assert all(r["evidence"]["association"] == "positional" for r in flat)


def test_grid_form_filled_and_degenerate_cells_skipped():
    doc = analyze(FIX / "target_grid.pdf", kind="fixed_layout")
    regions = _by_kind(doc, "overlay_region")
    fields = {r["payload"]["target_field"] for r in regions}
    assert "item" not in fields  # header cell itself (has text) not proposed
    for r in regions:  # no region narrower than the 12pt minimum (sliver column)
        x0, _, x1, _ = r["payload"]["bbox"]
        assert x1 - x0 >= 12


def test_grid_proposal_is_schema_valid():
    from rmu.onboard.schemas import validate_proposal

    validate_proposal(analyze(FIX / "target_grid.pdf", kind="fixed_layout"))


def test_label_box_template_does_not_trigger_grid_pass():
    """target_fixed.pdf has real label+box pairs: the box pass must keep
    handling it (no grid-evidence keys, same regions as before)."""
    doc = analyze(FIX / "target_fixed.pdf", kind="fixed_layout")
    regions = _by_kind(doc, "overlay_region")
    assert regions  # box pass found regions
    assert all("association" not in r["evidence"] for r in regions)
