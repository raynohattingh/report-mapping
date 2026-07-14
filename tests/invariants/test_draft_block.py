"""T009 — NEVER CUT (Constitution VIII, SC-006): a batch ApplyRun can only
reference human-approved registry artifacts. A draft onboarding proposal must
produce a clear pre-flight error BEFORE any record is read — the run is never
created, so the error is the CLI message (there is no exceptions report to
write into; kind 'draft_artifact' appears once a run context exists, T031)."""

from __future__ import annotations

import shutil

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from rmu.cli import app
from rmu.db import make_engine, make_session_factory
from rmu.models import ApplyRun, SourceDocument
from rmu.onboard.proposal import Proposal

runner = CliRunner()
SHA = "c" * 64


def _proposal_doc(kind: str) -> dict:
    element = {
        "id": "el-0",
        "element_kind": "header_field" if kind == "profile" else "form_field",
        "confidence": 0.9,
        "evidence": {"pages": [1], "source": "heuristic"},
        "review_state": "confirmed",
        "payload": {"name": "x"},
    }
    return {"kind": kind, "exemplars": [SHA], "elements": [element]}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    assert runner.invoke(app, ["seed", "load"]).exit_code == 0
    batch = tmp_path / "batch"
    batch.mkdir()
    shutil.copy("tests/fixtures/batch_20/synthetic_01.pdf", batch)
    factory = make_session_factory(make_engine())
    return batch, factory


def test_draft_profile_blocks_apply_with_clear_error(env):
    batch, factory = env
    with factory() as s:
        p = Proposal.create(s, _proposal_doc("profile"))
        draft_id = p.id

    result = runner.invoke(app, ["apply", "run", str(batch),
                                 "--transform", "newshape.pdf.survey@v1:interim.defect_csv@1"])
    assert result.exit_code == 1
    out = result.output
    assert "draft" in out and f"#{draft_id}" in out and "status=draft" in out
    assert "approved" in out  # tells the analyst the way forward

    with factory() as s:  # nothing ran, nothing ingested
        assert s.scalars(select(ApplyRun)).all() == []
        assert s.scalars(select(SourceDocument)).all() == []


def test_draft_template_blocks_apply_with_clear_error(env):
    batch, factory = env
    with factory() as s:
        p = Proposal.create(s, _proposal_doc("template"))
        draft_id = p.id

    result = runner.invoke(app, ["apply", "run", str(batch),
                                 "--transform", "scopito.pdf.powerline@v2020:ias.defect_form@1"])
    assert result.exit_code == 1
    assert f"#{draft_id}" in result.output and "status=draft" in result.output

    with factory() as s:
        assert s.scalars(select(ApplyRun)).all() == []


def test_unknown_ref_without_drafts_stays_a_plain_lookup_error(env):
    batch, _ = env
    result = runner.invoke(app, ["apply", "run", str(batch),
                                 "--transform", "nosuch.profile@v9:interim.defect_csv@1"])
    assert result.exit_code == 1
    assert "status=draft" not in result.output  # no phantom draft blame


def test_abandoned_drafts_never_get_the_blame(env):
    batch, factory = env
    with factory() as s:
        Proposal.create(s, _proposal_doc("profile")).mark_abandoned()

    result = runner.invoke(app, ["apply", "run", str(batch),
                                 "--transform", "nosuch.profile@v9:interim.defect_csv@1"])
    assert result.exit_code == 1
    assert "status=draft" not in result.output  # abandoned = no effect on anything


def test_identical_run_succeeds_once_the_draft_is_approved(tmp_path, monkeypatch):
    """T021 (SC-006 second half): the exact ref that failed while draft works
    after human approval — the wall is the status, not the ref."""
    import shutil

    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    monkeypatch.setenv("RMU_PROFILES", str(tmp_path / "profiles"))
    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    assert runner.invoke(app, ["seed", "load"]).exit_code == 0
    factory = make_session_factory(make_engine())

    from pathlib import Path as _P

    from rmu import store as blobstore
    from rmu.onboard.analyze_source import analyze
    from rmu.onboard.approve import approve_profile

    exemplar = _P("tests/fixtures/onboarding/survey_report_a.pdf")
    batch = tmp_path / "batch"
    batch.mkdir()
    shutil.copy("tests/fixtures/onboarding/survey_report_b.pdf", batch)
    transform_ref = "synthetic.pdf.survey@v1:interim.defect_csv@1"

    with factory() as s:
        blobstore.put_file(exemplar)
        document = analyze([exemplar])
        proposal = Proposal.create(s, document)

    blocked = runner.invoke(app, ["apply", "run", str(batch),
                                  "--transform", transform_ref])
    assert blocked.exit_code == 1 and "status=draft" in blocked.output

    with factory() as s:
        p = Proposal.load(s, proposal.id, sync=False)
        for e in p.document["elements"]:
            e["review_state"] = "confirmed"
        p.save_draft()
        p = Proposal.load(s, proposal.id)  # sync the confirmations
        approve_profile(s, p, "synthetic.pdf.survey", "v1", "rayno")

    from tests.integration.test_onboard_source_e2e import _approve_transform

    _approve_transform(tmp_path)
    converted = runner.invoke(app, ["apply", "run", str(batch),
                                    "--transform", transform_ref,
                                    "--answer", "contract_number=T021"])
    assert converted.exit_code == 0, converted.output
    assert "converted=1" in converted.output
