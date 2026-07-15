"""T032 (FR-032/FR-033a/FR-035, US4): spatial overlays project unchanged,
region drag/resize records a correction, analyst-drawn regions carry evidence
source 'analyst', and verify-on-approve failure returns a per-check report."""

from __future__ import annotations

import yaml
from sqlalchemy import select
from typer.testing import CliRunner

from rmu.db import make_engine, make_session_factory
from rmu.models import TargetTemplate

runner = CliRunner()


def _document(draft_path):
    return yaml.safe_load(draft_path.read_text(encoding="utf-8"))


def _first_region(draft_path):
    for e in _document(draft_path)["elements"]:
        if e["element_kind"] == "overlay_region":
            return e
    raise AssertionError("no overlay_region")


def test_geometry_projects_regions_with_page_and_bbox(studio_client, template_proposal):
    proposal_id, _ = template_proposal
    geo = studio_client.get(f"/proposals/{proposal_id}/geometry").json()
    assert geo["exemplars"]
    boxes = geo["exemplars"][0]["boxes"]
    assert boxes and all("bbox" in b and "page" in b for b in boxes)
    # cardinality (non-spatial) is listed, not drawn
    assert any(e["element_kind"] == "cardinality" for e in geo["non_spatial"])


def test_drag_resize_records_corrected_bbox(studio_client, template_proposal):
    proposal_id, draft_path = template_proposal
    region = _first_region(draft_path)
    new_bbox = [100.0, 700.0, 200.0, 720.0]
    response = studio_client.post(
        f"/proposals/{proposal_id}/elements/{region['id']}",
        data={"action": "correct",
              "payload": yaml.safe_dump({**region["payload"], "bbox": new_bbox})})
    assert response.status_code == 200, response.text
    el = next(e for e in _document(draft_path)["elements"] if e["id"] == region["id"])
    assert el["review_state"] == "corrected"
    assert el["corrected_payload"]["bbox"] == new_bbox


def test_analyst_drawn_region_carries_analyst_source(studio_client, template_proposal):
    proposal_id, draft_path = template_proposal
    payload = {"bbox": [50.0, 50.0, 150.0, 70.0], "kind": "text",
               "label": "missed", "page": 1, "target_field": "missed_field"}
    response = studio_client.post(
        f"/proposals/{proposal_id}/elements",
        data={"element_kind": "overlay_region", "payload": yaml.safe_dump(payload)})
    assert response.status_code == 200, response.text
    drawn = [e for e in _document(draft_path)["elements"]
             if e.get("evidence", {}).get("source") == "analyst"]
    assert len(drawn) == 1
    assert drawn[0]["payload"]["target_field"] == "missed_field"
    assert drawn[0]["review_state"] in ("confirmed", "corrected")


def test_verify_failure_returns_per_check_report(studio_client, template_proposal):
    """Confirm all regions but corrupt one bbox off-page so the round-trip
    verify fails; the proposal stays draft with the report shown per-check."""
    proposal_id, draft_path = template_proposal
    doc = _document(draft_path)
    for e in doc["elements"]:
        e["review_state"] = "confirmed"
    # shrink one region so its sample value cannot fit — an oversize render
    # problem (never silently truncated, D7) fails verify-on-approve
    for e in doc["elements"]:
        if e["element_kind"] == "overlay_region":
            x0, top, _x1, bottom = e["payload"]["bbox"]
            e["review_state"] = "corrected"
            e["corrected_payload"] = {**e["payload"],
                                      "bbox": [x0, top, x0 + 1.0, bottom]}
            break
    draft_path.write_text(yaml.safe_dump(doc, sort_keys=True))

    response = studio_client.post(
        f"/proposals/{proposal_id}/approve",
        data={"name": "grid.overlay@1", "by": "rayno"})
    assert response.status_code == 422, response.text
    assert "test_render" in response.text or "test_roundtrip" in response.text
    with make_session_factory(make_engine())() as s:
        assert not list(s.scalars(select(TargetTemplate).where(
            TargetTemplate.name == "grid.overlay")))  # nothing registered


def test_successful_approval_registers_and_offers_next_step(studio_client,
                                                            template_proposal):
    proposal_id, draft_path = template_proposal
    doc = _document(draft_path)
    for e in doc["elements"]:
        e["review_state"] = "confirmed"
    draft_path.write_text(yaml.safe_dump(doc, sort_keys=True))

    response = studio_client.post(
        f"/proposals/{proposal_id}/approve",
        data={"name": "grid.overlay@1", "by": "rayno"})
    assert response.status_code == 200, response.text
    assert "registered" in response.text.lower()
    assert "start" in response.text.lower()  # offers, never auto-starts (FR-035a)
    with make_session_factory(make_engine())() as s:
        rows = list(s.scalars(select(TargetTemplate).where(
            TargetTemplate.name == "grid.overlay")))
        assert len(rows) == 1 and rows[0].version == 1
