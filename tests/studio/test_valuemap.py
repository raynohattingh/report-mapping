"""T027 (FR-021, US3): link-level value maps stage in the session's draft
value-map file (NO registry write); an explicit Register & pin creates the
new append-only ValueMap version and pins name@version on the route."""

from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import select
from typer.testing import CliRunner

from rmu.cli import app
from rmu.db import make_engine, make_session_factory
from rmu.models import ValueMap
from rmu.studio.concurrency import content_hash

runner = CliRunner()
EXEMPLAR = "seed/source_samples/Distribution-report.pdf"


def _doc(draft_path) -> dict:
    return yaml.safe_load(draft_path.read_text(encoding="utf-8"))


def _hash(draft_path) -> str:
    return content_hash(draft_path.read_text(encoding="utf-8"))


def _staged_path(draft_path: Path, session_id: int, name: str) -> Path:
    return draft_path.parent / f"session_{session_id}.valuemap.{name}.yaml"


def test_link_detail_lists_observed_and_unmapped_values(studio_client, stub_session):
    session_id, _ = stub_session
    response = studio_client.get(f"/sessions/{session_id}/links/priority")
    assert response.status_code == 200, response.text
    # severity is observed 1-5/? on the Distribution exemplar
    assert "finding.severity" in response.text
    assert 'data-observed' in response.text


def test_stage_writes_draft_file_and_no_registry_row(studio_client, stub_session):
    session_id, draft_path = stub_session
    with make_session_factory(make_engine())() as s:
        before = len(list(s.scalars(select(ValueMap))))

    response = studio_client.post(
        f"/sessions/{session_id}/links/priority/valuemap",
        data={
            "name": "severity_to_priority",
            "source_value": ["1", "2", "9"],
            "target_value": ["P4", "P4", "P1"],
            "provenance": ["ai-accepted", "ai-accepted", "human"],
        },
    )
    assert response.status_code == 200, response.text

    staged = _staged_path(draft_path, session_id, "severity_to_priority")
    entries = yaml.safe_load(staged.read_text())["entries"]
    assert {e["source_value"] for e in entries} == {"1", "2", "9"}
    provs = {e["source_value"]: e["provenance"] for e in entries}
    assert provs["9"] == "human" and provs["1"] == "ai-accepted"

    with make_session_factory(make_engine())() as s:
        assert len(list(s.scalars(select(ValueMap)))) == before  # NO registry write


def test_register_and_pin_creates_version_and_pins_route(studio_client, stub_session):
    session_id, draft_path = stub_session
    studio_client.post(
        f"/sessions/{session_id}/links/priority/valuemap",
        data={"name": "severity_to_priority",
              "source_value": ["1", "5", "?"],
              "target_value": ["P4", "P1", "POI"],
              "provenance": ["ai-accepted", "human", "human"]},
    )
    response = studio_client.post(
        f"/sessions/{session_id}/links/priority/valuemap/register",
        data={"name": "severity_to_priority", "base_hash": _hash(draft_path)},
    )
    assert response.status_code == 200, response.text

    with make_session_factory(make_engine())() as s:
        rows = list(s.scalars(select(ValueMap).where(
            ValueMap.name == "severity_to_priority")))
        assert len(rows) == 1
        version = rows[0].version
        provs = {e["source_value"]: e["provenance"] for e in rows[0].entries}
        assert provs["5"] == "human" and provs["1"] == "ai-accepted"

    pin = _doc(draft_path)["routes"]["priority"]["value_map"]
    assert pin == {"name": "severity_to_priority", "version": version}


def test_register_matches_cli_valuemap_create(studio_client, stub_session, tmp_path):
    """The registered row is what `rmu valuemap create` would insert."""
    session_id, draft_path = stub_session
    entries = [{"source_value": "1", "target_value": "P4", "provenance": "ai-accepted"},
               {"source_value": "5", "target_value": "P1", "provenance": "human"}]
    studio_client.post(
        f"/sessions/{session_id}/links/priority/valuemap",
        data={"name": "severity_to_priority",
              "source_value": [e["source_value"] for e in entries],
              "target_value": [e["target_value"] for e in entries],
              "provenance": [e["provenance"] for e in entries]},
    )
    studio_client.post(
        f"/sessions/{session_id}/links/priority/valuemap/register",
        data={"name": "severity_to_priority", "base_hash": _hash(draft_path)},
    )
    # CLI creates the SAME entries under a different name → identical rows modulo name
    f = tmp_path / "vm.yaml"
    f.write_text(yaml.safe_dump({"entries": entries}))
    assert runner.invoke(app, ["valuemap", "create", "--name", "cli_severity",
                               "--file", str(f)]).exit_code == 0
    with make_session_factory(make_engine())() as s:
        studio_row = s.scalar(select(ValueMap).where(
            ValueMap.name == "severity_to_priority"))
        cli_row = s.scalar(select(ValueMap).where(ValueMap.name == "cli_severity"))
        assert studio_row.entries == cli_row.entries


def test_register_conflict_creates_no_orphan_version(studio_client, stub_session):
    """Review finding #1: a draft that changed underneath must 409 BEFORE any
    ValueMap version is created — no orphan, and a retry never double-registers
    (FR-003 row-parity on the FR-005 conflict path)."""
    session_id, draft_path = stub_session
    studio_client.post(
        f"/sessions/{session_id}/links/priority/valuemap",
        data={"name": "severity_to_priority",
              "source_value": ["1", "5"], "target_value": ["P4", "P1"],
              "provenance": ["human", "human"]})

    with make_session_factory(make_engine())() as s:
        before = len(list(s.scalars(select(ValueMap).where(
            ValueMap.name == "severity_to_priority"))))

    # register with a STALE hash (draft changed underneath) and no overwrite
    response = studio_client.post(
        f"/sessions/{session_id}/links/priority/valuemap/register",
        data={"name": "severity_to_priority", "base_hash": "0" * 64})
    assert response.status_code == 409, response.text

    with make_session_factory(make_engine())() as s:
        after = len(list(s.scalars(select(ValueMap).where(
            ValueMap.name == "severity_to_priority"))))
    assert after == before, "a conflicting register must not create a version"


def test_register_refuses_bad_provenance(studio_client, stub_session):
    session_id, draft_path = stub_session
    studio_client.post(
        f"/sessions/{session_id}/links/priority/valuemap",
        data={"name": "severity_to_priority",
              "source_value": ["1"], "target_value": ["P4"],
              "provenance": ["guessed"]},
    )
    response = studio_client.post(
        f"/sessions/{session_id}/links/priority/valuemap/register",
        data={"name": "severity_to_priority", "base_hash": _hash(draft_path)},
    )
    assert response.status_code == 422
    assert "provenance" in response.text
