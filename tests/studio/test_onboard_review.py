"""T031 (FR-033/FR-034, US4): confirm/correct/remove and bulk-confirm write
exactly the review_state/corrected_payload the YAML workflow writes, so CLI
review stays interchangeable; approval is blocked while any element is unreviewed."""

from __future__ import annotations

import yaml
from typer.testing import CliRunner

from rmu.cli import app
from rmu.db import make_engine, make_session_factory
from rmu.onboard.proposal import Proposal

runner = CliRunner()


def _document(draft_path):
    return yaml.safe_load(draft_path.read_text(encoding="utf-8"))


def _first_region(draft_path) -> str:
    for e in _document(draft_path)["elements"]:
        if e["element_kind"] == "overlay_region":
            return e["id"]
    raise AssertionError("no overlay_region element")


def test_confirm_writes_review_state_visible_to_cli(studio_client, template_proposal):
    proposal_id, draft_path = template_proposal
    eid = _first_region(draft_path)
    response = studio_client.post(
        f"/proposals/{proposal_id}/elements/{eid}", data={"action": "confirm"})
    assert response.status_code == 200, response.text

    # the CLI review sees the same state (YAML→DB sync round-trip)
    with make_session_factory(make_engine())() as s:
        p = Proposal.load(s, proposal_id)
        el = next(e for e in p.elements if e["id"] == eid)
        assert el["review_state"] == "confirmed"
    assert next(e for e in _document(draft_path)["elements"]
                if e["id"] == eid)["review_state"] == "confirmed"


def test_correct_writes_corrected_payload(studio_client, template_proposal):
    proposal_id, draft_path = template_proposal
    eid = _first_region(draft_path)
    original = next(e for e in _document(draft_path)["elements"] if e["id"] == eid)
    corrected = {**original["payload"], "target_field": "renamed_defect"}
    response = studio_client.post(
        f"/proposals/{proposal_id}/elements/{eid}",
        data={"action": "correct", "payload": yaml.safe_dump(corrected)})
    assert response.status_code == 200, response.text
    el = next(e for e in _document(draft_path)["elements"] if e["id"] == eid)
    assert el["review_state"] == "corrected"
    assert el["corrected_payload"]["target_field"] == "renamed_defect"


def test_remove_marks_element_removed(studio_client, template_proposal):
    proposal_id, draft_path = template_proposal
    eid = _first_region(draft_path)
    response = studio_client.post(
        f"/proposals/{proposal_id}/elements/{eid}", data={"action": "remove"})
    assert response.status_code == 200, response.text
    el = next(e for e in _document(draft_path)["elements"] if e["id"] == eid)
    assert el["review_state"] == "removed"


def test_bulk_confirm_records_each_element(studio_client, template_proposal):
    proposal_id, draft_path = template_proposal
    response = studio_client.post(
        f"/proposals/{proposal_id}/bulk-confirm", data={"page": "1"})
    assert response.status_code == 200, response.text
    states = {e["review_state"] for e in _document(draft_path)["elements"]
              if e["element_kind"] == "overlay_region"}
    assert states == {"confirmed"}  # every proposed region on page 1 confirmed


def test_approval_blocked_while_unreviewed(studio_client, template_proposal):
    proposal_id, _ = template_proposal
    response = studio_client.post(
        f"/proposals/{proposal_id}/approve",
        data={"name": "grid.form@1", "by": "rayno"})
    assert response.status_code == 422, response.text
    assert "unresolved" in response.text.lower() or "proposed" in response.text.lower()


def test_malformed_corrected_payload_returns_422(studio_client, template_proposal):
    """Review finding: a YAML typo in a correction must be a clean refusal."""
    proposal_id, draft_path = template_proposal
    eid = _first_region(draft_path)
    before = draft_path.read_bytes()
    response = studio_client.post(
        f"/proposals/{proposal_id}/elements/{eid}",
        data={"action": "correct", "payload": "bbox: [1, 2"})
    assert response.status_code == 422, response.text
    assert "not valid YAML" in response.text
    assert draft_path.read_bytes() == before


def test_terminal_proposal_is_read_only(studio_client, template_proposal, runner):
    proposal_id, draft_path = template_proposal
    assert runner.invoke(app, ["onboard", "abandon", str(proposal_id)]).exit_code == 0
    eid = _first_region(draft_path)
    response = studio_client.post(
        f"/proposals/{proposal_id}/elements/{eid}", data={"action": "confirm"})
    assert response.status_code == 422
    assert "terminal" in response.text or "abandoned" in response.text
