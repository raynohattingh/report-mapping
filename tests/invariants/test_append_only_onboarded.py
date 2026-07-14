"""T022 — NEVER CUT (Constitution III): registry rows PRODUCED by onboarding
are append-only like every other registry row, and provenance (SC-008) is
queryable: proposal -> who approved -> resulting artifact."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from rmu import store
from rmu.cli import app
from rmu.db import AppendOnlyViolation, make_engine, make_session_factory
from rmu.models import OnboardingProposal, SourceProfile
from rmu.onboard.analyze_source import analyze
from rmu.onboard.approve import approve_profile
from rmu.onboard.proposal import Proposal

runner = CliRunner()
EXEMPLAR = Path("tests/fixtures/onboarding/survey_report_a.pdf")


@pytest.fixture()
def session(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    monkeypatch.setenv("RMU_PROFILES", str(tmp_path / "profiles"))
    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    factory = make_session_factory(make_engine())
    with factory() as s:
        yield s


def _approved_profile(session) -> SourceProfile:
    store.put_file(EXEMPLAR)
    document = analyze([EXEMPLAR])
    for e in document["elements"]:
        e["review_state"] = "confirmed"
    proposal = Proposal.create(session, document)
    return approve_profile(session, proposal, "synthetic.pdf.survey", "v1", "rayno")


def test_onboarded_profile_rows_are_append_only(session):
    row = _approved_profile(session)

    row.job_type = "something-else"
    with pytest.raises(AppendOnlyViolation):
        session.commit()
    session.rollback()

    session.delete(session.get(SourceProfile, row.id))
    with pytest.raises(AppendOnlyViolation):
        session.commit()
    session.rollback()


def test_provenance_chain_is_queryable(session):
    row = _approved_profile(session)

    proposal_row = session.scalar(
        select(OnboardingProposal).where(
            OnboardingProposal.resulting_profile_id == row.id
        )
    )
    assert proposal_row is not None  # SC-008: artifact -> proposal
    assert proposal_row.approved_by == "rayno" and proposal_row.approved_at is not None
    assert proposal_row.verify_report["ok"] is True  # the machine-checked proof
    assert proposal_row.exemplar_shas  # which document it was learned from

    # and the CLI surfaces the lineage
    reviewed = runner.invoke(app, ["onboard", "review", str(proposal_row.id)])
    assert "approved by rayno" in reviewed.output
    assert f"profile_id={row.id}" in reviewed.output
