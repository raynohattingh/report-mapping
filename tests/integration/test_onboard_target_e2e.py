"""T027 + T031 — US3/US4 end-to-end: onboard PDF targets via the CLI, approve
through the test-render gate, then APPLY a batch into them: per-record filled
PDFs, round-trip verified on every render (FR-011/012/013), manifest hashes
identical across re-runs (FR-015)."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
import yaml
from pypdf import PdfReader
from typer.testing import CliRunner

from rmu.cli import app
from tests.integration.test_onboard_source_e2e import (
    DEFECT,
    PRIORITY,
    _onboard_and_approve,
)

runner = CliRunner()
FIX = Path("tests/fixtures/onboarding")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    monkeypatch.setenv("RMU_PROFILES", str(tmp_path / "profiles"))
    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    assert runner.invoke(app, ["seed", "load"]).exit_code == 0
    _onboard_and_approve(tmp_path)  # source profile synthetic.pdf.survey@v1
    return tmp_path


def _onboard_template(fixture: str, name: str) -> None:
    drafted = runner.invoke(app, ["onboard", "draft-template", str(FIX / fixture)])
    assert drafted.exit_code == 0, drafted.output
    proposal_id = re.search(r"proposal: (\d+)", drafted.output).group(1)
    draft_path = Path(re.search(r"draft: (\S+)", drafted.output).group(1))

    document = yaml.safe_load(draft_path.read_text())
    for element in document["elements"]:
        element["review_state"] = "confirmed"
    draft_path.write_text(yaml.safe_dump(document, sort_keys=True))

    approved = runner.invoke(app, ["onboard", "approve", proposal_id,
                                   "--name", name, "--by", "rayno"])
    assert approved.exit_code == 0, approved.output


def _approve_transform(tmp_path, template_ref: str, routes: dict,
                       constants: dict) -> None:
    started = runner.invoke(app, [
        "map", "start", "--profile", "synthetic.pdf.survey@v1",
        "--template", template_ref,
        "--exemplar", str(FIX / "survey_report_a.pdf"), "--no-ai",
    ])
    assert started.exit_code == 0, started.output
    session_id = re.search(r"session: (\d+)", started.output).group(1)
    draft = Path(re.search(r"draft:\s+(\S+)", started.output).group(1))

    for name, entries in [("survey_priority", PRIORITY), ("survey_defect", DEFECT)]:
        f = tmp_path / f"vm_{name}_{template_ref.replace('@','_')}.yaml"
        f.write_text(yaml.safe_dump({"entries": entries}))
        runner.invoke(app, ["valuemap", "create", "--name", name, "--file", str(f)])

    doc = yaml.safe_load(draft.read_text())
    doc["routes"] = routes
    doc["constants"] = constants
    doc["prompts"] = []
    draft.write_text(yaml.safe_dump(doc, sort_keys=True))
    approved = runner.invoke(app, ["map", "approve", "--session", session_id,
                                   "--by", "rayno"])
    assert approved.exit_code == 0, approved.output


def test_form_target_batch_renders_and_roundtrips(env):
    _onboard_template("target_form.pdf", "ias.defect_form@1")
    _approve_transform(env, "ias.defect_form@1", routes={
        "asset_id": {"from": "header.site", "tier": "T0"},
        "defect_code": {"from": "finding.class", "tier": "T1",
                        "value_map": {"name": "survey_defect", "version": 1}},
        "priority": {"from": "finding.class", "tier": "T1",
                     "value_map": {"name": "survey_priority", "version": 1}},
        "comments": {"from": "finding.observation", "tier": "T0"},
    }, constants={"reinspect": "yes"})

    batch = env / "batch_form"
    batch.mkdir()
    shutil.copy(FIX / "survey_report_b.pdf", batch)

    hashes = []
    for _ in range(2):  # FR-015: re-run determinism at the batch level
        result = runner.invoke(app, ["apply", "run", str(batch),
                                     "--transform",
                                     "synthetic.pdf.survey@v1:ias.defect_form@1"])
        assert result.exit_code == 0, result.output
        assert "converted=1" in result.output
        run_dir = Path(result.output.split("outputs: ")[1].splitlines()[0].strip())
        pdfs = sorted(run_dir.glob("*.ias.defect_form.*.pdf"))
        assert len(pdfs) == 9  # per_record: one filled PDF per record (US4)
        hashes.append({p.name: p.read_bytes() for p in pdfs})

        # independent read-back of the first output (SC-004)
        fields = PdfReader(pdfs[0]).get_fields()
        # the fixture generator prints the same Site: line on every survey
        assert str(fields["asset_id"].value) == "Feeder 11 North"
        assert str(fields["priority"].value) in {"P1", "P2", "P3", "P4"}
        assert str(fields["reinspect"].value) == "/Yes"

        exceptions = (run_dir / "exceptions.csv").read_text()
        assert "render_roundtrip" not in exceptions  # every render verified clean
    assert hashes[0] == hashes[1]


def test_overlay_target_batch_renders_at_coordinates(env):
    _onboard_template("target_fixed.pdf", "ias.record_sheet@1")
    _approve_transform(env, "ias.record_sheet@1", routes={
        "asset_id": {"from": "header.site", "tier": "T0"},
        "defect_code": {"from": "finding.class", "tier": "T1",
                        "value_map": {"name": "survey_defect", "version": 1}},
        "priority": {"from": "finding.class", "tier": "T1",
                     "value_map": {"name": "survey_priority", "version": 1}},
        "observation": {"from": "finding.observation", "tier": "T0"},
        "photo": {"from": "finding.photo_ref", "tier": "T0"},
    }, constants={"inspection_date": "2026-07-03"})

    batch = env / "batch_overlay"
    batch.mkdir()
    shutil.copy(FIX / "survey_report_b.pdf", batch)

    result = runner.invoke(app, ["apply", "run", str(batch),
                                 "--transform",
                                 "synthetic.pdf.survey@v1:ias.record_sheet@1"])
    assert result.exit_code == 0, result.output
    run_dir = Path(result.output.split("outputs: ")[1].splitlines()[0].strip())
    pdfs = sorted(run_dir.glob("*.ias.record_sheet.*.pdf"))
    assert len(pdfs) == 9

    import pdfplumber

    with pdfplumber.open(pdfs[0]) as pdf:
        text = pdf.pages[0].extract_text()
        assert "Feeder 11 North" in text  # value present as real text (read-back)
        assert len(pdf.pages[0].images) >= 1  # the record photo placed (FR-012a)
    assert "render_roundtrip" not in (run_dir / "exceptions.csv").read_text()


def test_per_batch_cardinality_renders_one_pdf(env):
    """T040 (FR-009): a template whose reviewed cardinality is per_batch
    produces exactly ONE verified PDF from a multi-record batch. Also asserts
    T037: shipped PDF outputs carry roundtrip=verified in the audit manifest."""
    drafted = runner.invoke(app, ["onboard", "draft-template",
                                  str(FIX / "target_form.pdf")])
    proposal_id = re.search(r"proposal: (\d+)", drafted.output).group(1)
    draft_path = Path(re.search(r"draft: (\S+)", drafted.output).group(1))
    document = yaml.safe_load(draft_path.read_text())
    for element in document["elements"]:
        element["review_state"] = "confirmed"
        if element["element_kind"] == "cardinality":
            element["review_state"] = "corrected"
            element["corrected_payload"] = {"cardinality": "per_batch"}
    draft_path.write_text(yaml.safe_dump(document, sort_keys=True))
    approved = runner.invoke(app, ["onboard", "approve", proposal_id,
                                   "--name", "ias.batch_form@1", "--by", "rayno"])
    assert approved.exit_code == 0, approved.output

    _approve_transform(env, "ias.batch_form@1", routes={
        "asset_id": {"from": "header.site", "tier": "T0"},
        "defect_code": {"from": "finding.class", "tier": "T1",
                        "value_map": {"name": "survey_defect", "version": 1}},
        "priority": {"from": "finding.class", "tier": "T1",
                     "value_map": {"name": "survey_priority", "version": 1}},
        "comments": {"from": "finding.observation", "tier": "T0"},
    }, constants={"reinspect": "yes"})

    batch = env / "batch_perbatch"
    batch.mkdir()
    shutil.copy(FIX / "survey_report_b.pdf", batch)
    result = runner.invoke(app, ["apply", "run", str(batch),
                                 "--transform",
                                 "synthetic.pdf.survey@v1:ias.batch_form@1"])
    assert result.exit_code == 0, result.output
    run_dir = Path(result.output.split("outputs: ")[1].splitlines()[0].strip())
    pdfs = sorted(run_dir.glob("*.ias.batch_form*.pdf"))
    assert len(pdfs) == 1  # ONE document for the whole batch

    # T037: the audit manifest records the round-trip verification
    from sqlalchemy import select

    from rmu.db import make_engine, make_session_factory
    from rmu.models import ApplyRun

    factory = make_session_factory(make_engine())
    with factory() as s:
        run = s.scalars(select(ApplyRun).order_by(ApplyRun.id.desc())).first()
        pdf_entries = [m for m in run.outputs_manifest
                       if m["output_kind"] == "pdf_form"]
        assert pdf_entries and all(m["roundtrip"] == "verified" for m in pdf_entries)
