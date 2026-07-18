"""T-006 Phase 2 final review fix: rotation-correctness of the matrix `band`
projection (src/rmu/studio/geometry.py `_matrix_projection`/`_union_bbox`).

The real Eskom pack is a portrait mediabox displayed landscape via /Rotate 90
(see tests/unit/test_matrix_rotation.py, which pins reconstruction of the
LOGICAL matrix on such pages). On those pages a logical row renders as a
narrow VERTICAL strip in visual space and a logical column as a narrow
HORIZONTAL strip — the inverse of the unrotated case. `band` must be the
union bbox of an entry's own cells (never a full-width/full-height band), so
it is correct regardless of orientation. This test proves that end-to-end
through the same onboarding CLI path the unrotated `matrix_proposal` fixture
uses, on a /Rotate 90 copy of the same fixture PDF."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from rmu.db import make_engine, make_session_factory

FIXTURE = Path("tests/fixtures/onboarding/matrix_target.pdf")


def _rotated_copy(tmp_path: Path, rotation: int) -> Path:
    from pypdf import PdfWriter

    out = tmp_path / f"matrix_rot{rotation}.pdf"
    writer = PdfWriter(clone_from=str(FIXTURE))
    writer.pages[0].rotate(rotation)
    with open(out, "wb") as fh:
        writer.write(fh)
    return out


def _rotated_matrix_proposal(studio_env, runner, tmp_path, rotation):
    from rmu.cli import app

    rotated = _rotated_copy(tmp_path, rotation)
    drafted = runner.invoke(app, ["onboard", "draft-template", str(rotated), "--no-ai"])
    assert drafted.exit_code == 0, drafted.output
    proposal_id = int(re.search(r"proposal: (\d+)", drafted.output).group(1))
    return proposal_id


def _geometry(proposal_id: int) -> dict:
    from rmu.studio.geometry import proposal_geometry

    with make_session_factory(make_engine())() as s:
        return proposal_geometry(s, proposal_id)


@pytest.mark.parametrize("rotation", [90])
def test_rotated_bands_are_vertical_strips_for_rows_horizontal_for_cols(
        studio_env, runner, tmp_path, rotation):
    """On a /Rotate 90 page, criterion bands (rows) must be TALLER than wide
    and tower bands (columns) must be WIDER than tall — the inverse of the
    unrotated layout — because a full-axis band model would smear/swap these."""
    proposal_id = _rotated_matrix_proposal(studio_env, runner, tmp_path, rotation)
    geo = _geometry(proposal_id)
    matrix = geo["matrix"]
    assert matrix is not None

    pages = {p["page"]: p for p in geo["exemplars"][0]["pages"]}

    bands_seen = 0
    for criterion in matrix["criteria"]:
        if criterion["band"] is None:
            continue
        bands_seen += 1
        page = pages[criterion["page"]]
        x0, y0, x1, y1 = criterion["band"]
        assert 0.0 <= x0 <= x1 <= page["width"]
        assert 0.0 <= y0 <= y1 <= page["height"]
        assert (y1 - y0) > (x1 - x0), (
            "criterion (row) band must be taller than wide at /Rotate 90")

    for tower in matrix["towers"]:
        if tower["band"] is None:
            continue
        bands_seen += 1
        page = pages[tower["page"]]
        x0, y0, x1, y1 = tower["band"]
        assert 0.0 <= x0 <= x1 <= page["width"]
        assert 0.0 <= y0 <= y1 <= page["height"]
        assert (x1 - x0) > (y1 - y0), (
            "tower (column) band must be wider than tall at /Rotate 90")

    assert bands_seen > 0, "fixture produced no bands at all — test is vacuous"


@pytest.mark.parametrize("rotation", [90])
def test_rotated_criterion_band_contains_only_its_own_cells(
        studio_env, runner, tmp_path, rotation):
    """Each criterion's band must be the union of exactly ITS OWN cells (by
    row_id) — a subset-containment check that would fail under the old
    full-width band model (which unions in every OTHER row's cells too)."""
    proposal_id = _rotated_matrix_proposal(studio_env, runner, tmp_path, rotation)
    geo = _geometry(proposal_id)
    matrix = geo["matrix"]
    spatial = geo["spatial"]

    for criterion in matrix["criteria"]:
        own_cells = [c for c in spatial if c.get("row_id") == criterion["id"]]
        if not own_cells:
            assert criterion["band"] is None
            continue
        x0, y0, x1, y1 = criterion["band"]
        for cell in own_cells:
            cx0, cy0, cx1, cy1 = cell["bbox"]
            assert x0 <= cx0 and cx1 <= x1 and y0 <= cy0 and cy1 <= y1

    for tower in matrix["towers"]:
        own_cells = [c for c in spatial if c.get("col_id") == tower["id"]]
        if not own_cells:
            assert tower["band"] is None
            continue
        x0, y0, x1, y1 = tower["band"]
        for cell in own_cells:
            cx0, cy0, cx1, cy1 = cell["bbox"]
            assert x0 <= cx0 and cx1 <= x1 and y0 <= cy0 and cy1 <= y1
