"""T015 (FR-013/FR-013a/FR-014, US1): every canvas mutation writes the same
bytes the library-path edit writes, validates before writing, and respects
the DraftLease. Uses the T012 parity harness."""

from __future__ import annotations

import yaml

from rmu.studio import draftedit
from rmu.studio.concurrency import content_hash
from tests.studio.parity import assert_studio_matches_library


def _hash(draft_path) -> str:
    return content_hash(draft_path.read_text(encoding="utf-8"))


def _doc(draft_path) -> dict:
    return yaml.safe_load(draft_path.read_text(encoding="utf-8"))


def _t2_fields(draft_path) -> list[str]:
    return [f for f, r in _doc(draft_path)["routes"].items() if r["tier"] == "T2"]


def test_create_manual_route_matches_library_edit(studio_client, stub_session):
    """Reject a proposal, then draw the same field manually — the everyday
    'the AI was wrong, I know the right source' flow."""
    session_id, draft_path = stub_session
    field = _t2_fields(draft_path)[2]
    rejected = studio_client.post(
        f"/sessions/{session_id}/routes/{field}",
        data={"action": "reject", "base_hash": _hash(draft_path)},
    )
    assert rejected.status_code == 200, rejected.text
    response = assert_studio_matches_library(
        draft_path,
        lambda doc: draftedit.create_route(doc, field, "finding.comments"),
        lambda: studio_client.post(
            f"/sessions/{session_id}/routes",
            data={"field": field, "source": "finding.comments",
                  "base_hash": _hash(draft_path)},
        ),
    )
    assert response.status_code == 200, response.text
    assert _doc(draft_path)["routes"][field]["tier"] == "T0"  # FR-013a


def test_draw_link_fills_a_seeded_t3_stub(manual_session):
    """`map start` seeds every required field as a T3 stub (from='?'). The
    primary draw gesture (source→target, FR-013) MUST fill that stub in, not
    refuse it — otherwise no required field can be mapped on the canvas (the
    everyday flow). Regression: create_route used to refuse any field already
    present in routes, which is every required field."""
    _, draft_path = manual_session
    doc = _doc(draft_path)
    field = "source_severity"
    assert doc["routes"][field]["tier"] == "T3", "precondition: seeded stub"
    draftedit.create_route(doc, field, "finding.severity")
    assert doc["routes"][field]["from"] == "finding.severity"
    assert doc["routes"][field]["tier"] in ("T0", "T1")


def test_draw_link_still_refuses_over_a_confirmed_route(manual_session):
    """Drawing over a real (non-T3) route is still refused — the analyst is
    directed to re-route/accept, so a confirmed mapping is never clobbered."""
    import pytest

    _, draft_path = manual_session
    doc = _doc(draft_path)
    field = "source_severity"
    draftedit.create_route(doc, field, "finding.severity")  # now confirmed
    with pytest.raises(draftedit.RouteEditError):
        draftedit.create_route(doc, field, "finding.comments")


def test_accept_promotes_to_derived_tier(studio_client, stub_session):
    session_id, draft_path = stub_session
    field = _t2_fields(draft_path)[0]
    response = assert_studio_matches_library(
        draft_path,
        lambda doc: draftedit.accept_route(doc, field),
        lambda: studio_client.post(
            f"/sessions/{session_id}/routes/{field}",
            data={"action": "accept", "base_hash": _hash(draft_path)},
        ),
    )
    assert response.status_code == 200, response.text
    route = _doc(draft_path)["routes"][field]
    assert route["tier"] == ("T1" if route.get("value_map") else "T0")


def test_reject_removes_route(studio_client, stub_session):
    session_id, draft_path = stub_session
    field = _t2_fields(draft_path)[1]
    response = assert_studio_matches_library(
        draft_path,
        lambda doc: draftedit.reject_route(doc, field),
        lambda: studio_client.post(
            f"/sessions/{session_id}/routes/{field}",
            data={"action": "reject", "base_hash": _hash(draft_path)},
        ),
    )
    assert response.status_code == 200, response.text
    assert field not in _doc(draft_path)["routes"]


def test_reroute_records_new_source_and_recomputes_tier(studio_client, stub_session):
    session_id, draft_path = stub_session
    field = _t2_fields(draft_path)[0]
    response = assert_studio_matches_library(
        draft_path,
        lambda doc: draftedit.reroute(doc, field, "finding.comments"),
        lambda: studio_client.post(
            f"/sessions/{session_id}/routes/{field}",
            data={"action": "reroute", "source": "finding.comments",
                  "base_hash": _hash(draft_path)},
        ),
    )
    assert response.status_code == 200, response.text
    route = _doc(draft_path)["routes"][field]
    assert route["from"] == "finding.comments"
    assert route["tier"] in ("T0", "T1")


def test_schema_invalid_edit_refused_before_write(studio_client, stub_session):
    session_id, draft_path = stub_session
    before = draft_path.read_bytes()
    response = studio_client.post(
        f"/sessions/{session_id}/routes",
        data={"field": "comments", "source": "", "base_hash": _hash(draft_path)},
    )
    assert response.status_code == 422, response.text
    assert draft_path.read_bytes() == before  # validated BEFORE write


def test_stale_hash_conflicts_with_409(studio_client, stub_session):
    session_id, draft_path = stub_session
    before = draft_path.read_bytes()
    response = studio_client.post(
        f"/sessions/{session_id}/routes",
        data={"field": "comments", "source": "finding.comments",
              "base_hash": "0" * 64},
    )
    assert response.status_code == 409, response.text
    assert draft_path.read_bytes() == before


def test_corrupt_draft_get_returns_422_not_500(studio_client, manual_session):
    """Review finding #3: a hand-corrupted draft must surface as a clean
    refusal on a GET, never a 500."""
    session_id, draft_path = manual_session
    draft_path.write_text("routes: [this is not a valid transform\n", encoding="utf-8")
    response = studio_client.get(f"/sessions/{session_id}/fragments/links")
    assert response.status_code == 422, response.text
    assert "schema-valid" in response.text or "not valid" in response.text.lower()


def test_terminal_session_mutations_refused(studio_client, manual_session, runner):
    """FR-006: approved/abandoned sessions are read-only in the studio."""
    from rmu.cli import app

    session_id, draft_path = manual_session
    assert runner.invoke(app, ["map", "abandon", "--session", str(session_id)]
                         ).exit_code == 0
    response = studio_client.post(
        f"/sessions/{session_id}/routes",
        data={"field": "comments", "source": "finding.comments",
              "base_hash": _hash(draft_path)},
    )
    assert response.status_code == 422
    assert "terminal" in response.text
