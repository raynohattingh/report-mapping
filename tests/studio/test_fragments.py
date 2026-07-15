"""T016 (FR-018/FR-019): the readiness bar IS the gate; the link list keeps
T3 gaps loud and filters by state."""

from __future__ import annotations

from rmu.db import make_engine, make_session_factory


def _gate(session_id: int) -> dict:
    from rmu.mapping.approve import gate_state
    from rmu.mapping.loader import parse_transform
    from rmu.mapping.start import load_session_state
    from rmu.registry import get_template_by_id, required_fields

    with make_session_factory(make_engine())() as s:
        ms, draft_path, _ = load_session_state(s, session_id)
        template = get_template_by_id(s, ms.target_template_id)
        doc = parse_transform(draft_path.read_text())
        return gate_state(doc, required_fields(template), s)


def test_readiness_bar_shows_gate_numbers(studio_client, stub_session):
    session_id, _ = stub_session
    gate = _gate(session_id)
    response = studio_client.get(f"/sessions/{session_id}/fragments/readiness")
    assert response.status_code == 200, response.text
    assert f"{gate['ready']}/{gate['total_required']} fields ready" in response.text
    assert f"{len(gate['t2_pending'])} pending" in response.text
    assert f"{len(gate['t3_unmapped'])} unmapped" in response.text


def test_readiness_never_ready_while_gate_refuses(studio_client, stub_session):
    session_id, _ = stub_session
    gate = _gate(session_id)
    assert not gate["approvable"]
    response = studio_client.get(f"/sessions/{session_id}/fragments/readiness")
    assert "Approve" not in response.text or "disabled" in response.text


def test_link_list_marks_missing_required_fields_red(studio_client, stub_session):
    session_id, _ = stub_session
    response = studio_client.get(f"/sessions/{session_id}/fragments/links")
    assert response.status_code == 200
    assert 'link-row missing' in response.text  # T3 entries are red rows (FR-018)


def test_link_list_filters_by_state(studio_client, stub_session):
    session_id, _ = stub_session
    everything = studio_client.get(f"/sessions/{session_id}/fragments/links").text
    pending = studio_client.get(
        f"/sessions/{session_id}/fragments/links", params={"state": "pending"}
    ).text
    missing = studio_client.get(
        f"/sessions/{session_id}/fragments/links", params={"state": "missing"}
    ).text
    assert everything.count("link-row") > pending.count("link-row")
    assert "tier-T2" in pending and "tier-T3" not in pending
    assert "tier-T2" not in missing
