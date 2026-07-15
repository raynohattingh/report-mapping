"""T014 (FR-011/FR-012/FR-013a, SC-007's testable half).

Geometry is a PROJECTION: registered coordinates pass through unchanged in
the rotation-aware visual space pdfplumber reports; the client only scales.
Elements without coordinates fall to panels, never disappear.
"""

from __future__ import annotations

import pdfplumber

from rmu.db import make_engine, make_session_factory


def _geometry(session_id: int) -> dict:
    from rmu.studio.geometry import session_geometry

    with make_session_factory(make_engine())() as s:
        return session_geometry(s, session_id)


def _rotated_pdf(path, rotation: int) -> None:
    """A portrait A4 page displayed landscape-via-/Rotate — the same geometry
    as the real landscape-via-rotation target packs (SC-001 fixture stays
    quarantined; this synthetic stand-in proves the projection contract)."""
    from pypdf import PdfWriter
    from reportlab.pdfgen import canvas

    base = path.with_suffix(".base.pdf")
    c = canvas.Canvas(str(base), pagesize=(595.0, 842.0))  # portrait mediabox
    c.drawString(100, 700, "cell")
    c.showPage()
    c.save()
    writer = PdfWriter(clone_from=str(base))
    writer.pages[0].rotate(rotation)
    with open(path, "wb") as fh:
        writer.write(fh)


def test_source_elements_without_coordinates_fall_to_panel(manual_session):
    session_id, _ = manual_session
    geo = _geometry(session_id)
    panel_keys = {e["key"] for e in geo["source"]["panel"]}
    assert "header.company" in panel_keys
    assert "finding.severity" in panel_keys
    # the seed v2020 profile registers no spatial anchors — nothing invented
    assert geo["source"]["boxes"] == []


def test_record_table_columns_carry_observed_samples(manual_session):
    session_id, _ = manual_session
    geo = _geometry(session_id)
    severity = next(e for e in geo["source"]["panel"]
                    if e["key"] == "finding.severity")
    assert severity["observed"], "record-table column must show observed values"
    assert set(severity["observed"]) <= {"1", "2", "3", "4", "5", "?"}


def test_source_pages_reported_with_visual_dims(manual_session):
    session_id, _ = manual_session
    geo = _geometry(session_id)
    assert geo["source"]["pdf_sha"]
    assert geo["source"]["page_count"] > 0


def test_csv_target_presents_structured_panel(manual_session):
    session_id, _ = manual_session
    geo = _geometry(session_id)
    assert geo["target"]["kind"] == "csv"
    fields = {f["field"] for f in geo["target"]["panel"]}
    assert "priority" in fields and "defect_code" in fields
    assert geo["target"]["boxes"] == []


def test_links_project_routes_with_stable_tags_and_states(manual_session):
    session_id, _ = manual_session
    geo = _geometry(session_id)
    links = geo["links"]
    by_field = {link["target_field"]: link for link in links}
    # manual --no-ai draft: every required field is a T3 placeholder
    assert by_field["priority"]["tier"] == "T3"
    assert by_field["priority"]["state"] == "missing"
    tags = [link["tag"] for link in links]
    assert tags == sorted(tags) == list(range(1, len(links) + 1))


def test_gate_matches_check_approval(manual_session):
    """FR-019: the readiness numbers ARE the gate, not a parallel calculation."""
    from rmu.mapping.approve import ApprovalRefused, check_approval
    from rmu.mapping.loader import parse_transform
    from rmu.registry import get_template_by_id, required_fields

    session_id, draft_path = manual_session
    geo = _geometry(session_id)
    with make_session_factory(make_engine())() as s:
        from rmu.mapping.start import load_session_state

        ms, _, _ = load_session_state(s, session_id)
        template = get_template_by_id(s, ms.target_template_id)
        doc = parse_transform(draft_path.read_text())
        try:
            check_approval(doc, required_fields(template), s)
            gate_refuses = False
        except ApprovalRefused:
            gate_refuses = True
    assert geo["gate"]["approvable"] == (not gate_refuses)
    assert geo["gate"]["t3_unmapped"], "fresh manual draft must show T3 blockers"


def test_source_boxes_tolerate_missing_profile_recipe():
    """An onboarded profile whose recipe YAML was removed (a real dev-DB state)
    must not crash the canvas: the CLI review/preview succeed from the stored
    extraction, so the studio must too (FR-002). Spatial boxes simply fall away
    — nothing is invented, nothing 500s."""
    from rmu.studio.geometry import _source_boxes

    dims = [{"page": 1, "width": 595.0, "height": 842.0}]
    assert _source_boxes("no.such.profile@1", dims) == []


def test_registered_bboxes_project_unchanged_in_visual_space(tmp_path):
    """A registered bbox is emitted verbatim; a page displayed landscape via
    /Rotate 90 on a portrait mediabox reports VISUAL (rotated) dims — the same
    geometry as the real landscape-via-rotation packs."""
    from rmu.studio.geometry import page_dimensions, project_box

    box = {"field": "cell", "page": 2, "bbox": [100.0, 700.0, 160.0, 716.0]}
    assert project_box(box)["bbox"] == [100.0, 700.0, 160.0, 716.0]

    rotated = tmp_path / "rotated.pdf"
    _rotated_pdf(rotated, 90)
    dims = page_dimensions(rotated)
    with pdfplumber.open(rotated) as pdf:
        for reported, page in zip(dims, pdf.pages, strict=True):
            assert reported["width"] == float(page.width)
            assert reported["height"] == float(page.height)
    # portrait mediabox (595×842) displayed via /Rotate 90 → landscape visual dims
    assert dims[0]["width"] > dims[0]["height"], (
        "rotated page's visual dims must reflect the rotation"
    )
