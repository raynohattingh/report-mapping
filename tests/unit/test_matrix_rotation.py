"""Rotated-page matrix reconstruction (feature 005 follow-up, pre-Eskom gate).

The real Eskom pack is a portrait mediabox displayed landscape via /Rotate 90.
All other matrix fixtures are unrotated, so rotation behaviour was unpinned —
and the 003 render layer had real rotation bugs before. This fixture is the
committed matrix grid re-wrapped with /Rotate; reconstruction must yield the
SAME logical matrix (criteria, towers, cells) with bboxes in the rotation-aware
VISUAL space pdfplumber reports (the same space overlays and renderers use).
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber
import pytest

from rmu.onboard.matrix import reconstruct_matrix

FIXTURE = Path("tests/fixtures/onboarding/matrix_target.pdf")


def _rotated_copy(tmp_path: Path, rotation: int) -> Path:
    from pypdf import PdfWriter

    out = tmp_path / f"matrix_rot{rotation}.pdf"
    writer = PdfWriter(clone_from=str(FIXTURE))
    writer.pages[0].rotate(rotation)
    with open(out, "wb") as fh:
        writer.write(fh)
    return out


def _by_kind(elements: list[dict], kind: str) -> list[dict]:
    return [e for e in elements if e["element_kind"] == kind]


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_rotated_matrix_reconstructs_same_logical_structure(tmp_path, rotation):
    rotated = _rotated_copy(tmp_path, rotation)
    elements = reconstruct_matrix(rotated)
    assert elements is not None, f"/Rotate {rotation}: no grid found at all"

    row_axis = _by_kind(elements, "row_axis")[0]["payload"]
    col_axis = _by_kind(elements, "col_axis")[0]["payload"]
    assert [e["number"] for e in row_axis["entries"]] == ["4.1", "4.2", "4.3"]
    assert [e["label"] for e in row_axis["entries"]] == [
        "Broken stay wire", "Corrosion", "Bird streamer"]
    assert [e["label"] for e in col_axis["entries"]] == ["T1", "T2", "T3"]

    cells = _by_kind(elements, "overlay_region")
    assert len(cells) == 9
    assert {c["payload"]["target_field"] for c in cells} == {
        f"{r}__{t}" for r in ("broken_stay_wire", "corrosion", "bird_streamer")
        for t in ("t1", "t2", "t3")}


@pytest.mark.parametrize("rotation", [90, 180])
def test_rotated_extract_grids_feeds_interpret_clean_text(tmp_path, rotation):
    """The interpret stage's grid input must be the LOGICAL grid — without
    derotation a 90-degree page hands the AI a transposed grid and a
    180-degree page literally reversed text ('noisorroC')."""
    from rmu.onboard.matrix import extract_grids

    grids = extract_grids(_rotated_copy(tmp_path, rotation))
    assert grids[1][0] == ["No", "Criterion", "T1", "T2", "T3"]
    assert grids[1][2][1] == "Corrosion"


@pytest.mark.parametrize("rotation", [90, 270])
def test_rotated_cell_bboxes_land_in_visual_space(tmp_path, rotation):
    """Cell bboxes must be valid in the VISUAL (post-rotation) page space —
    inside the visual page bounds, in the renderer's bottom-left y-up frame
    (matrix.py flips pdfplumber's top-down y exactly like analyze_target)."""
    rotated = _rotated_copy(tmp_path, rotation)
    with pdfplumber.open(rotated) as pdf:
        vw, vh = float(pdf.pages[0].width), float(pdf.pages[0].height)
    # sanity: the fixture mediabox is landscape A4; /Rotate 90|270 displays it
    # portrait, and pdfplumber reports those VISUAL (post-rotation) dims.
    assert vh > vw

    elements = reconstruct_matrix(rotated)
    cells = _by_kind(elements, "overlay_region")
    for c in cells:
        x0, y0, x1, y1 = c["payload"]["bbox"]
        assert 0 <= x0 < x1 <= vw + 0.5, (c["payload"]["target_field"], c["payload"]["bbox"])
        assert 0 <= y0 < y1 <= vh + 0.5, (c["payload"]["target_field"], c["payload"]["bbox"])
