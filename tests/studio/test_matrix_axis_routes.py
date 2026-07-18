"""T-006 Phase 2 Task 2: axis entry review routes — zero studio business logic.

Each route composes a full new `entries` list and calls the EXISTING
Proposal.set_review_state('corrected'/'confirmed') path (the same write path
YAML hand-edits and the generic element route use) — never writes YAML
directly. Parity tests assert the studio result equals the equivalent
library-path edit, byte-for-byte."""

from __future__ import annotations

import yaml
from typer.testing import CliRunner

from rmu.cli import app
from tests.studio.parity import assert_studio_matches_library

runner = CliRunner()


def _document(draft_path):
    return yaml.safe_load(draft_path.read_text(encoding="utf-8"))


def _row_axis_id(draft_path) -> str:
    for e in _document(draft_path)["elements"]:
        if e["element_kind"] == "row_axis":
            return e["id"]
    raise AssertionError("no row_axis element")


def _seed_suggestion(draft_path, element_id: str, index: int, *,
                     label: str, number: str | None = None,
                     confidence: float = 0.9) -> None:
    """Seed suggested_* onto one axis entry by editing the draft YAML
    directly (the shared-file contract) — no interpret-stage AI needed."""
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


def test_rename_writes_corrected_payload_others_untouched(studio_client, matrix_proposal):
    proposal_id, draft_path = matrix_proposal
    eid = _row_axis_id(draft_path)
    before = _document(draft_path)
    before_entries = before["elements"][
        [e["id"] for e in before["elements"]].index(eid)]["payload"]["entries"]

    response = studio_client.post(
        f"/proposals/{proposal_id}/axis/{eid}/entries/1",
        data={"action": "rename", "label": "Renamed Corrosion", "number": "9.9"})
    assert response.status_code == 200, response.text

    after = _document(draft_path)
    element = next(e for e in after["elements"] if e["id"] == eid)
    assert element["review_state"] == "corrected"
    entries = element["corrected_payload"]["entries"]
    assert entries[1]["label"] == "Renamed Corrosion"
    assert entries[1]["number"] == "9.9"
    assert "suggested_label" not in entries[1]
    # every OTHER entry byte-identical to before
    for i, entry in enumerate(entries):
        if i == 1:
            continue
        assert entry == before_entries[i]


def test_rename_is_parity_with_library_edit(studio_client, matrix_proposal):
    proposal_id, draft_path = matrix_proposal
    eid = _row_axis_id(draft_path)

    def mutate(doc):
        element = next(e for e in doc["elements"] if e["id"] == eid)
        entries = [dict(e) for e in element["payload"]["entries"]]
        entries[0]["label"] = "Broken stay wire (renamed)"
        element["review_state"] = "corrected"
        element["corrected_payload"] = {**element["payload"], "entries": entries}

    assert_studio_matches_library(
        draft_path, mutate,
        lambda: studio_client.post(
            f"/proposals/{proposal_id}/axis/{eid}/entries/0",
            data={"action": "rename", "label": "Broken stay wire (renamed)"}),
    )


def test_accept_suggestion_applies_and_strips(studio_client, matrix_proposal):
    proposal_id, draft_path = matrix_proposal
    eid = _row_axis_id(draft_path)
    _seed_suggestion(draft_path, eid, 2, label="Bird Streamer (AI)", number="4.30")

    def mutate(doc):
        element = next(e for e in doc["elements"] if e["id"] == eid)
        entries = [dict(e) for e in element["payload"]["entries"]]
        entries[2]["label"] = entries[2]["suggested_label"]
        entries[2]["number"] = entries[2]["suggested_number"]
        for key in ("suggested_label", "suggested_number", "suggested_confidence"):
            entries[2].pop(key, None)
        element["review_state"] = "corrected"
        element["corrected_payload"] = {**element["payload"], "entries": entries}

    assert_studio_matches_library(
        draft_path, mutate,
        lambda: studio_client.post(
            f"/proposals/{proposal_id}/axis/{eid}/entries/2",
            data={"action": "accept_suggestion"}),
    )

    element = next(e for e in _document(draft_path)["elements"] if e["id"] == eid)
    entry = element["corrected_payload"]["entries"][2]
    assert entry["label"] == "Bird Streamer (AI)"
    assert entry["number"] == "4.30"
    assert "suggested_label" not in entry
    assert "suggested_number" not in entry
    assert "suggested_confidence" not in entry


def test_reject_suggestion_strips_only(studio_client, matrix_proposal):
    proposal_id, draft_path = matrix_proposal
    eid = _row_axis_id(draft_path)
    _seed_suggestion(draft_path, eid, 0, label="Broken Stay Wire (AI)")
    original_label = _document(draft_path)["elements"][0]["payload"]["entries"][0]["label"]

    response = studio_client.post(
        f"/proposals/{proposal_id}/axis/{eid}/entries/0",
        data={"action": "reject_suggestion"})
    assert response.status_code == 200, response.text

    element = next(e for e in _document(draft_path)["elements"] if e["id"] == eid)
    entry = element["corrected_payload"]["entries"][0]
    assert entry["label"] == original_label
    assert "suggested_label" not in entry
    assert "suggested_confidence" not in entry


def test_accept_suggestion_without_suggestion_is_422(studio_client, matrix_proposal):
    proposal_id, draft_path = matrix_proposal
    eid = _row_axis_id(draft_path)
    before = draft_path.read_bytes()
    response = studio_client.post(
        f"/proposals/{proposal_id}/axis/{eid}/entries/0",
        data={"action": "accept_suggestion"})
    assert response.status_code == 422, response.text
    assert draft_path.read_bytes() == before


def test_unknown_entry_index_is_422(studio_client, matrix_proposal):
    proposal_id, draft_path = matrix_proposal
    eid = _row_axis_id(draft_path)
    response = studio_client.post(
        f"/proposals/{proposal_id}/axis/{eid}/entries/99",
        data={"action": "rename", "label": "x"})
    assert response.status_code == 422, response.text


def test_unknown_element_is_422(studio_client, matrix_proposal):
    proposal_id, _ = matrix_proposal
    response = studio_client.post(
        f"/proposals/{proposal_id}/axis/no-such-element/entries/0",
        data={"action": "rename", "label": "x"})
    assert response.status_code == 422, response.text


def test_confirm_marks_element_confirmed(studio_client, matrix_proposal):
    proposal_id, draft_path = matrix_proposal
    eid = _row_axis_id(draft_path)
    response = studio_client.post(f"/proposals/{proposal_id}/axis/{eid}/confirm")
    assert response.status_code == 200, response.text
    element = next(e for e in _document(draft_path)["elements"] if e["id"] == eid)
    assert element["review_state"] == "confirmed"
    assert "corrected_payload" not in element


def test_confirm_is_parity_with_library_edit(studio_client, matrix_proposal):
    proposal_id, draft_path = matrix_proposal
    eid = _row_axis_id(draft_path)

    def mutate(doc):
        element = next(e for e in doc["elements"] if e["id"] == eid)
        element["review_state"] = "confirmed"
        element.pop("corrected_payload", None)

    assert_studio_matches_library(
        draft_path, mutate,
        lambda: studio_client.post(f"/proposals/{proposal_id}/axis/{eid}/confirm"),
    )


def test_terminal_proposal_is_read_only(studio_client, matrix_proposal, runner):
    proposal_id, draft_path = matrix_proposal
    assert runner.invoke(app, ["onboard", "abandon", str(proposal_id)]).exit_code == 0
    eid = _row_axis_id(draft_path)
    response = studio_client.post(
        f"/proposals/{proposal_id}/axis/{eid}/entries/0",
        data={"action": "rename", "label": "x"})
    assert response.status_code == 422
    assert "terminal" in response.text or "abandoned" in response.text

    response = studio_client.post(f"/proposals/{proposal_id}/axis/{eid}/confirm")
    assert response.status_code == 422
