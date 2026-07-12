"""T018 — verify-on-approve for profiles (FR-017/FR-022/FR-024, SC-002).

The gate must fail CLOSED: mismatch and collision leave the proposal in draft
with the report persisted; only a full pass registers a SourceProfile."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from rmu import store
from rmu.cli import app
from rmu.config import profiles_root
from rmu.db import make_engine, make_session_factory
from rmu.onboard.analyze_source import analyze
from rmu.onboard.approve import VerifyFailure, approve_profile
from rmu.onboard.proposal import Proposal
from rmu.seed import profile_config

runner = CliRunner()
FIX = Path("tests/fixtures/onboarding")
EXEMPLAR = FIX / "survey_report_a.pdf"


@pytest.fixture()
def session(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    monkeypatch.setenv("RMU_PROFILES", str(tmp_path / "profiles"))
    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    factory = make_session_factory(make_engine())
    with factory() as s:
        yield s


def _confirmed_proposal(session, corrupt: dict | None = None) -> Proposal:
    store.put_file(EXEMPLAR)
    document = analyze([EXEMPLAR])
    for e in document["elements"]:
        e["review_state"] = "confirmed"
    if corrupt:
        target = next(e for e in document["elements"] if e["id"] == corrupt["id"])
        target.update(corrupt["patch"])
    return Proposal.create(session, document)


def test_happy_path_registers_profile_with_provenance(session):
    p = _confirmed_proposal(session)
    row = approve_profile(session, p, "synthetic.pdf.survey", "v1", "rayno")

    assert row.key == "synthetic.pdf.survey" and row.extractor_ref == "rmu.extract.recipe_pdf"
    assert (profiles_root() / "synthetic.pdf.survey.v1.yaml").exists()
    assert p.status == "approved" and p.row.approved_by == "rayno"  # FR-017
    assert p.row.resulting_profile_id == row.id
    assert p.row.verify_report["ok"] is True

    # the registered recipe extracts deterministically via the generic engine
    from rmu.extract.recipe_pdf import extract

    normalized = extract(EXEMPLAR, profile_config("synthetic.pdf.survey@v1"))
    assert len(normalized["findings"]) == 26  # SC-002: validated subset, 100%


def test_header_mismatch_fails_closed(session):
    p = _confirmed_proposal(
        session,
        corrupt={
            "id": "hdr-0",
            "patch": {"payload": {"name": "survey_date", "strategy": "label_right",
                                  "labels": ["Survey date:"],
                                  "example_value": "NOT THE REAL DATE"}},
        },
    )
    with pytest.raises(VerifyFailure) as exc:
        approve_profile(session, p, "synthetic.pdf.survey", "v1", "rayno")

    assert p.status == "draft"  # returned to review, not registered
    assert p.row.verify_report and p.row.verify_report["ok"] is False
    failed = [c for c in p.row.verify_report["checks"] if not c["ok"]]
    assert any("header" in c["check"] for c in failed)
    assert "extracted" in str(exc.value)
    assert not (profiles_root() / "synthetic.pdf.survey.v1.yaml").exists()


def test_fingerprint_collision_blocks_second_profile(session):
    first = _confirmed_proposal(session)
    approve_profile(session, first, "synthetic.pdf.survey", "v1", "rayno")

    second = _confirmed_proposal(session)
    with pytest.raises(VerifyFailure) as exc:
        approve_profile(session, second, "another.pdf.survey", "v1", "rayno")

    assert "synthetic.pdf.survey@v1" in str(exc.value)  # names the colliding profile
    assert second.status == "draft"
