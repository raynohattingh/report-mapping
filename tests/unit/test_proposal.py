"""T007 — proposal lifecycle: draft persistence, per-element review states,
approval blocking on unresolved elements (FR-003/FR-005), and the only legal
state transitions draft→approved / draft→abandoned."""

from __future__ import annotations

import pytest
import yaml
from typer.testing import CliRunner

from rmu.cli import app
from rmu.db import make_engine, make_session_factory
from rmu.onboard.proposal import (
    Proposal,
    ProposalStateError,
    UnresolvedElementsError,
)
from rmu.onboard.schemas import SchemaValidationError

runner = CliRunner()
SHA = "b" * 64


def _doc(states: list[str]) -> dict:
    return {
        "kind": "profile",
        "exemplars": [SHA],
        "elements": [
            {
                "id": f"el-{i}",
                "element_kind": "header_field",
                "confidence": 0.7,
                "evidence": {"pages": [1], "source": "heuristic"},
                "review_state": state,
                "payload": {"name": f"field_{i}"},
            }
            for i, state in enumerate(states)
        ],
    }


@pytest.fixture()
def session(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    factory = make_session_factory(make_engine())
    with factory() as s:
        yield s


def test_create_persists_draft_row_and_yaml(session):
    p = Proposal.create(session, _doc(["proposed", "proposed"]))
    assert p.status == "draft"
    assert p.draft_path().exists()
    assert p.unresolved() == ["el-0", "el-1"]


def test_invalid_document_rejected_before_persist(session):
    with pytest.raises(SchemaValidationError):
        Proposal.create(session, {"kind": "profile"})  # missing exemplars/elements


def test_analyst_yaml_edits_sync_on_load(session):
    p = Proposal.create(session, _doc(["proposed"]))
    doc = yaml.safe_load(p.draft_path().read_text())
    doc["elements"][0]["review_state"] = "confirmed"
    p.draft_path().write_text(yaml.safe_dump(doc, sort_keys=True))

    reloaded = Proposal.load(session, p.id)
    assert reloaded.unresolved() == []


def test_approval_blocked_while_any_element_unresolved(session):
    p = Proposal.create(session, _doc(["confirmed", "proposed", "removed"]))
    with pytest.raises(UnresolvedElementsError) as exc:
        p.ensure_approvable()
    assert "el-1" in str(exc.value)  # names what blocks approval (FR-003)


def test_mark_approved_records_who_when_and_locks(session):
    p = Proposal.create(session, _doc(["confirmed"]))
    p.ensure_approvable()
    p.mark_approved("rayno", verify_report={"ok": True}, resulting_profile_id=None)
    assert p.status == "approved"
    assert p.row.approved_by == "rayno"
    assert p.row.approved_at is not None
    with pytest.raises(ProposalStateError):
        p.mark_abandoned()  # no transition out of approved


def test_abandoned_is_terminal_and_harmless(session):
    p = Proposal.create(session, _doc(["proposed"]))
    p.mark_abandoned()
    assert p.status == "abandoned"
    with pytest.raises(ProposalStateError):
        p.mark_approved("rayno", verify_report={})
    # abandoned drafts keep their YAML for the audit trail but block nothing
    assert Proposal.load(session, p.id).status == "abandoned"


def test_verify_failure_keeps_draft_and_persists_report(session):
    p = Proposal.create(session, _doc(["confirmed"]))
    p.record_verify_failure({"ok": False, "mismatches": ["el-0"]})
    assert p.status == "draft"
    assert p.row.verify_report == {"ok": False, "mismatches": ["el-0"]}
