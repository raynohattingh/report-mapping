"""T-006 Phase 2 Task 1: matrix projection in studio geometry.

`proposal_geometry` gains a derived `matrix` block for grid targets (feature
005 row_axis/col_axis + cell overlay_regions): axis entries enriched with
review state and suggestion fields, plus a per-entry `band` — the union bbox
of ONLY that entry's own cells (row_id for criteria, col_id for towers).
Deliberately not a single-axis (full-width/full-height) band: on rotated
pages a logical row/column is a strip, not a full-page band (see
tests/studio/test_matrix_geometry_rotated.py). Pure projection — nothing new
is stored (Constitution/D6)."""

from __future__ import annotations

from rmu.db import make_engine, make_session_factory


def _geometry(proposal_id: int) -> dict:
    from rmu.studio.geometry import proposal_geometry

    with make_session_factory(make_engine())() as s:
        return proposal_geometry(s, proposal_id)


def test_matrix_block_present_with_criteria_and_towers(matrix_proposal):
    proposal_id, _ = matrix_proposal
    geo = _geometry(proposal_id)

    matrix = geo["matrix"]
    assert matrix is not None
    assert len(matrix["criteria"]) == 3
    numbers = {c["number"] for c in matrix["criteria"]}
    assert numbers == {"4.1", "4.2", "4.3"}
    assert len(matrix["towers"]) == 3
    assert matrix["cell_count"] == 9


def test_bands_lie_within_page_dims(matrix_proposal):
    proposal_id, _ = matrix_proposal
    geo = _geometry(proposal_id)

    matrix = geo["matrix"]
    pages = {p["page"]: p for p in geo["exemplars"][0]["pages"]}

    for criterion in matrix["criteria"]:
        if criterion["band"] is None:
            continue
        page = pages[criterion["page"]]
        x0, y0, x1, y1 = criterion["band"]
        assert 0.0 <= x0 <= x1 <= page["width"]
        assert 0.0 <= y0 <= y1 <= page["height"]

    for tower in matrix["towers"]:
        if tower["band"] is None:
            continue
        page = pages[tower["page"]]
        x0, y0, x1, y1 = tower["band"]
        assert 0.0 <= x0 <= x1 <= page["width"]
        assert 0.0 <= y0 <= y1 <= page["height"]


def test_axis_entries_carry_review_state_and_suggestion_fields(matrix_proposal):
    proposal_id, _ = matrix_proposal
    geo = _geometry(proposal_id)

    matrix = geo["matrix"]
    assert matrix["row_state"] == "proposed"
    assert matrix["col_state"] == "proposed"
    for criterion in matrix["criteria"]:
        assert "suggested_label" in criterion
        assert "suggested_number" in criterion
        assert "confidence" in criterion
        # --no-ai draft: no interpret-stage suggestions landed
        assert criterion["suggested_label"] is None
        assert criterion["suggested_number"] is None
        assert criterion["confidence"] is None
    for tower in matrix["towers"]:
        assert "suggested_label" in tower
        assert "confidence" in tower
        assert tower["suggested_label"] is None
        assert tower["confidence"] is None


def test_non_matrix_proposal_yields_matrix_none(no_grid_proposal):
    proposal_id, _ = no_grid_proposal
    geo = _geometry(proposal_id)
    assert geo["matrix"] is None
