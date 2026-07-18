"""T-006 Phase 2 Task 3: axis rail template + matrix branch of proposal.html.

The proposal view renders a criteria/towers axis rail (from geo.matrix)
instead of the generic per-element triage rail when the proposal has a
projected matrix (feature 005 row_axis/col_axis grid). Read-only (terminal)
proposals render the same panels with zero hx-post affordances (FR-006).
Non-matrix proposals keep rendering the existing generic rail unchanged."""

from __future__ import annotations

import re

import yaml
from typer.testing import CliRunner

from rmu.cli import app

runner = CliRunner()


def _document(draft_path):
    return yaml.safe_load(draft_path.read_text(encoding="utf-8"))


def _row_axis_id(draft_path) -> str:
    for e in _document(draft_path)["elements"]:
        if e["element_kind"] == "row_axis":
            return e["id"]
    raise AssertionError("no row_axis element")


def _col_axis_id(draft_path) -> str:
    for e in _document(draft_path)["elements"]:
        if e["element_kind"] == "col_axis":
            return e["id"]
    raise AssertionError("no col_axis element")


def _seed_suggestion(draft_path, element_id: str, index: int, *,
                     label: str, number: str | None = None,
                     confidence: float = 0.9) -> None:
    doc = _document(draft_path)
    for e in doc["elements"]:
        if e["id"] == element_id:
            entry = e["payload"]["entries"][index]
            entry["suggested_label"] = label
            entry["suggested_confidence"] = confidence
            if number is not None:
                entry["suggested_number"] = number
            break
    else:
        raise AssertionError(f"no element {element_id!r}")
    draft_path.write_text(yaml.safe_dump(doc, sort_keys=True))


def test_matrix_view_shows_criteria_and_towers_panels(studio_client, matrix_proposal):
    proposal_id, draft_path = matrix_proposal
    row_eid = _row_axis_id(draft_path)
    col_eid = _col_axis_id(draft_path)

    response = studio_client.get(f"/proposals/{proposal_id}")
    assert response.status_code == 200, response.text
    body = response.text

    assert "criteria" in body.lower()
    assert "tower" in body.lower()

    doc = _document(draft_path)
    row_el = next(e for e in doc["elements"] if e["id"] == row_eid)
    for entry in row_el["payload"]["entries"]:
        assert entry["number"] in body
        assert entry["label"] in body

    for index in range(len(row_el["payload"]["entries"])):
        assert f'data-axis-entry="{row_eid}:{index}"' in body

    col_el = next(e for e in doc["elements"] if e["id"] == col_eid)
    for index in range(len(col_el["payload"]["entries"])):
        assert f'data-axis-entry="{col_eid}:{index}"' in body

    assert f"/proposals/{proposal_id}/axis/{row_eid}/entries/" in body
    assert f"/proposals/{proposal_id}/axis/{row_eid}/confirm" in body
    assert "9 cells derive from these axes" in body


def test_pending_suggestion_shows_confidence_chip_and_accept_reject(
        studio_client, matrix_proposal):
    proposal_id, draft_path = matrix_proposal
    row_eid = _row_axis_id(draft_path)
    _seed_suggestion(draft_path, row_eid, 1, label="Bird Streamer (AI)",
                     number="4.20", confidence=0.87)

    response = studio_client.get(f"/proposals/{proposal_id}")
    assert response.status_code == 200, response.text
    body = response.text

    assert "Bird Streamer (AI)" in body
    assert "0.87" in body
    assert f"/proposals/{proposal_id}/axis/{row_eid}/entries/1" in body
    assert "accept_suggestion" in body
    assert "reject_suggestion" in body


def test_terminal_matrix_proposal_has_no_hx_post_affordances(
        studio_client, matrix_proposal, runner):
    proposal_id, draft_path = matrix_proposal
    assert runner.invoke(app, ["onboard", "abandon", str(proposal_id)]).exit_code == 0

    response = studio_client.get(f"/proposals/{proposal_id}")
    assert response.status_code == 200, response.text
    body = response.text

    assert "criteria" in body.lower()
    assert "tower" in body.lower()
    assert "hx-post" not in body


def test_non_matrix_proposal_still_renders_generic_rail(studio_client, no_grid_proposal):
    proposal_id, _ = no_grid_proposal
    response = studio_client.get(f"/proposals/{proposal_id}")
    assert response.status_code == 200, response.text
    body = response.text

    # regression guard: same generic-rail markup asserted by the pre-existing
    # onboarding-review coverage (test_onboard_review.py exercises the
    # /elements/{id} routes this heading's rows post to).
    assert re.search(r"spatial elements \(\d+\)", body)
    assert 'id="triage-rail"' in body
    assert "data-axis-entry" not in body
