"""T028 (FR-013a/FR-022, US3): constants, closed-grammar formulas and
per-batch prompts land in the draft exactly as the transform schema defines;
the derived tier recomputes when the mechanism changes."""

from __future__ import annotations

import yaml

from rmu.studio.concurrency import content_hash


def _doc(draft_path) -> dict:
    return yaml.safe_load(draft_path.read_text(encoding="utf-8"))


def _hash(draft_path) -> str:
    return content_hash(draft_path.read_text(encoding="utf-8"))


def test_set_constant_moves_field_to_constants(studio_client, stub_session):
    session_id, draft_path = stub_session
    response = studio_client.post(
        f"/sessions/{session_id}/links/inspection_method/mechanism",
        data={"mechanism": "constant", "value": "UAV visual",
              "base_hash": _hash(draft_path)},
    )
    assert response.status_code == 200, response.text
    doc = _doc(draft_path)
    assert doc["constants"]["inspection_method"] == "UAV visual"
    assert "inspection_method" not in doc.get("routes", {})


def test_set_formula_stores_closed_grammar_spec(studio_client, stub_session):
    session_id, draft_path = stub_session
    spec = {"fn": "date_format",
            "args": [{"field": "header.report_date"}, {"lit": "%Y-%m-%d"}]}
    response = studio_client.post(
        f"/sessions/{session_id}/links/inspection_date/mechanism",
        data={"mechanism": "formula", "spec": yaml.safe_dump(spec),
              "base_hash": _hash(draft_path)},
    )
    assert response.status_code == 200, response.text
    assert _doc(draft_path)["formulas"]["inspection_date"] == spec


def test_invalid_formula_refused_by_schema_before_write(studio_client, stub_session):
    session_id, draft_path = stub_session
    before = draft_path.read_bytes()
    spec = {"fn": "not_a_real_fn", "args": []}  # outside the closed grammar
    response = studio_client.post(
        f"/sessions/{session_id}/links/inspection_date/mechanism",
        data={"mechanism": "formula", "spec": yaml.safe_dump(spec),
              "base_hash": _hash(draft_path)},
    )
    assert response.status_code == 422, response.text
    assert draft_path.read_bytes() == before


def test_malformed_formula_yaml_returns_422_not_500(studio_client, stub_session):
    """Review finding: analyst YAML typos must be a clean refusal, not a 500."""
    session_id, draft_path = stub_session
    before = draft_path.read_bytes()
    response = studio_client.post(
        f"/sessions/{session_id}/links/inspection_date/mechanism",
        data={"mechanism": "formula", "spec": "fn: [unclosed",
              "base_hash": _hash(draft_path)},
    )
    assert response.status_code == 422, response.text
    assert "not valid YAML" in response.text
    assert draft_path.read_bytes() == before


def test_set_prompt_adds_per_batch_prompt(studio_client, stub_session):
    session_id, draft_path = stub_session
    response = studio_client.post(
        f"/sessions/{session_id}/links/contract_number/mechanism",
        data={"mechanism": "prompt", "key": "contract_number",
              "label": "Client contract number", "required": "true",
              "base_hash": _hash(draft_path)},
    )
    assert response.status_code == 200, response.text
    prompts = _doc(draft_path)["prompts"]
    assert any(p["key"] == "contract_number" and p["required"] for p in prompts)


def test_pinning_value_map_recomputes_tier_to_t1(studio_client, stub_session):
    """FR-013a: a route gains a value map → tier recomputes T0→T1."""
    session_id, draft_path = stub_session
    # first reject the proposal and draw a plain deterministic route (T0)
    studio_client.post(f"/sessions/{session_id}/routes/priority",
                       data={"action": "reject", "base_hash": _hash(draft_path)})
    studio_client.post(f"/sessions/{session_id}/routes",
                       data={"field": "priority", "source": "finding.severity",
                             "base_hash": _hash(draft_path)})
    assert _doc(draft_path)["routes"]["priority"]["tier"] == "T0"

    # stage + register a value map, then pin it — tier must become T1
    studio_client.post(
        f"/sessions/{session_id}/links/priority/valuemap",
        data={"name": "sev_pri", "source_value": ["1"], "target_value": ["P4"],
              "provenance": ["human"]},
    )
    response = studio_client.post(
        f"/sessions/{session_id}/links/priority/valuemap/register",
        data={"name": "sev_pri", "base_hash": _hash(draft_path)},
    )
    assert response.status_code == 200, response.text
    assert _doc(draft_path)["routes"]["priority"]["tier"] == "T1"
