"""T-006 Phase 2 Task 5: the full axis-first review journey over HTTP.

Proves the whole surface end-to-end (TestClient, no browser): studio
initiation (upload) -> library-seeded suggestions (shared draft file, FR-002)
-> axis entry edits + axis confirm + bulk-confirm over HTTP -> approve ->
review decisions land in the registered TargetTemplate.required_schema
-> the draft stays loadable by the CLI review path (interchangeability
smoke, FR-033)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from typer.testing import CliRunner

from rmu.cli import app
from rmu.db import make_engine, make_session_factory
from rmu.models import TargetTemplate
from rmu.onboard.interpret_matrix import StubAxisInterpreter, apply_interpretation
from rmu.onboard.matrix import extract_grids
from rmu.onboard.proposal import Proposal

runner = CliRunner()
MATRIX_PDF = "tests/fixtures/onboarding/matrix_target.pdf"


def _upload_matrix(studio_client) -> int:
    with open(MATRIX_PDF, "rb") as fh:
        response = studio_client.post(
            "/start/onboarding",
            data={"kind": "template"},
            files={"document": ("matrix_target.pdf", fh, "application/pdf")},
        )
    assert response.status_code == 200, response.text
    return int(re.search(r"[Pp]roposal (\d+)", response.text).group(1))


def _seed_suggestions(proposal_id: int) -> None:
    """Seed suggested_* onto two row_axis entries via the real feature-005
    library path (apply_interpretation + StubAxisInterpreter over the grid
    extracted from the uploaded PDF) — persisted through the SAME shared
    draft file the studio and CLI both read (FR-002), using Proposal's own
    load/save mechanics rather than hand-writing YAML."""
    interpreter = StubAxisInterpreter({
        "row_axis": {
            "entries": [
                {"row": 2, "number": "4.2", "label": "Corrosion (AI)", "confidence": 0.9},
                {"row": 3, "number": "4.3", "label": "Bird Streamer (AI)", "confidence": 0.85},
            ]
        },
    })
    grids = extract_grids(Path(MATRIX_PDF))
    factory = make_session_factory(make_engine())
    with factory() as s:
        p = Proposal.load(s, proposal_id, sync=False)
        apply_interpretation(p.document, grids, interpreter)
        p.save_draft()
        s.commit()


def _row_col_axis_ids(draft_path: Path) -> tuple[str, str]:
    doc = yaml.safe_load(draft_path.read_text())
    row_id = next(e["id"] for e in doc["elements"] if e["element_kind"] == "row_axis")
    col_id = next(e["id"] for e in doc["elements"] if e["element_kind"] == "col_axis")
    return row_id, col_id


def test_matrix_studio_review_journey(studio_client, studio_env):
    proposal_id = _upload_matrix(studio_client)
    draft_path = studio_env / "drafts" / f"onboard_{proposal_id}.yaml"
    assert draft_path.exists()

    _seed_suggestions(proposal_id)

    row_eid, col_eid = _row_col_axis_ids(draft_path)

    # rename criterion 0 ("Broken stay wire") — no suggestion involved.
    response = studio_client.post(
        f"/proposals/{proposal_id}/axis/{row_eid}/entries/0",
        data={"action": "rename", "label": "Broken Stay Wire (Renamed)"})
    assert response.status_code == 200, response.text

    # accept the AI suggestion on criterion 1 ("Corrosion").
    response = studio_client.post(
        f"/proposals/{proposal_id}/axis/{row_eid}/entries/1",
        data={"action": "accept_suggestion"})
    assert response.status_code == 200, response.text

    # reject the AI suggestion on criterion 2 ("Bird streamer") — original stands.
    response = studio_client.post(
        f"/proposals/{proposal_id}/axis/{row_eid}/entries/2",
        data={"action": "reject_suggestion"})
    assert response.status_code == 200, response.text

    doc = yaml.safe_load(draft_path.read_text())
    row_element = next(e for e in doc["elements"] if e["id"] == row_eid)
    assert row_element["review_state"] == "corrected"
    entries = row_element["corrected_payload"]["entries"]
    assert entries[0]["label"] == "Broken Stay Wire (Renamed)"
    assert entries[1]["label"] == "Corrosion (AI)"
    assert entries[1]["number"] == "4.2"
    assert "suggested_label" not in entries[1]
    assert entries[2]["label"] == "Bird streamer"  # original — suggestion rejected
    assert "suggested_label" not in entries[2]

    # confirm both axes: the row axis already carries corrections (state
    # 'corrected') and must stay that way — confirming it must not discard
    # the rename/accept just recorded; the (unedited) column axis moves
    # proposed -> confirmed.
    response = studio_client.post(f"/proposals/{proposal_id}/axis/{row_eid}/confirm")
    assert response.status_code == 200, response.text
    response = studio_client.post(f"/proposals/{proposal_id}/axis/{col_eid}/confirm")
    assert response.status_code == 200, response.text

    doc = yaml.safe_load(draft_path.read_text())
    row_element = next(e for e in doc["elements"] if e["id"] == row_eid)
    col_element = next(e for e in doc["elements"] if e["id"] == col_eid)
    assert row_element["review_state"] == "corrected"
    assert row_element["corrected_payload"]["entries"][1]["label"] == "Corrosion (AI)"
    assert col_element["review_state"] == "confirmed"
    assert "corrected_payload" not in col_element

    # remaining cell + cardinality elements (all page 1, still 'proposed')
    # via the existing bulk-confirm route.
    response = studio_client.post(f"/proposals/{proposal_id}/bulk-confirm",
                                  data={"page": 1})
    assert response.status_code == 200, response.text

    doc = yaml.safe_load(draft_path.read_text())
    assert all(e["review_state"] != "proposed" for e in doc["elements"])

    # approve.
    response = studio_client.post(f"/proposals/{proposal_id}/approve",
                                  data={"name": "matrix.e2e@1"})
    assert response.status_code == 200, response.text
    assert "matrix.e2e" in response.text

    # review decisions flow into the registered artifact.
    factory = make_session_factory(make_engine())
    with factory() as s:
        row = s.query(TargetTemplate).filter_by(name="matrix.e2e").one()
    schema = row.required_schema
    criteria_labels = {c["label"] for c in schema["matrix"]["criteria"]}
    assert "Broken Stay Wire (Renamed)" in criteria_labels
    assert "Corrosion (AI)" in criteria_labels
    assert "Bird streamer" in criteria_labels

    # interchangeability smoke: the (now-approved, terminal) draft is still
    # loadable read-only by the CLI review path.
    reviewed = runner.invoke(app, ["onboard", "review", str(proposal_id)])
    assert reviewed.exit_code == 0, reviewed.output
    assert "approved by" in reviewed.output
