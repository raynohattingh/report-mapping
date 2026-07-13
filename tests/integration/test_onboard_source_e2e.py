"""T020 — US1 end-to-end: draft-profile → analyst corrections → verify-on-
approve → registered profile auto-detects and CONVERTS same-shape PDFs through
the existing map/apply pipeline with zero new pipeline code (FR-018).
Drifted input stays out (fingerprint) with the FR-021 onboarding hint; misuse
warns (FR-023); prose takes the skeleton path (FR-001b)."""

from __future__ import annotations

import csv
import re
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from rmu.cli import app

runner = CliRunner()
FIX = Path("tests/fixtures/onboarding")

PRIORITY = [{"source_value": s, "target_value": t, "provenance": "human"}
            for s, t in [("Structural", "P2"), ("Electrical", "P1"),
                         ("Vegetation", "P3"), ("Corrosion", "P4")]]
# survey classes -> the template's registered severity vocabulary (1-5/?)
SEVERITY = [{"source_value": s, "target_value": t, "provenance": "human"}
            for s, t in [("Structural", "2"), ("Electrical", "1"),
                         ("Vegetation", "3"), ("Corrosion", "4")]]
DEFECT = [{"source_value": s, "target_value": t, "provenance": "human"}
          for s, t in [("Structural", "C1"), ("Electrical", "F1"),
                       ("Vegetation", "F12"), ("Corrosion", "A3")]]


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    monkeypatch.setenv("RMU_PROFILES", str(tmp_path / "profiles"))
    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    assert runner.invoke(app, ["seed", "load"]).exit_code == 0
    return tmp_path


def _onboard_and_approve(tmp_path) -> None:
    drafted = runner.invoke(
        app, ["onboard", "draft-profile", str(FIX / "survey_report_a.pdf"), "--no-ai"]
    )
    assert drafted.exit_code == 0, drafted.output
    proposal_id = re.search(r"proposal: (\d+)", drafted.output).group(1)
    draft_path = Path(re.search(r"draft: (\S+)", drafted.output).group(1))
    assert Path(re.search(r"review sheet: (\S+)", drafted.output).group(1)).exists()

    # analyst review: confirm everything, correct one field name (FR-003)
    document = yaml.safe_load(draft_path.read_text())
    for element in document["elements"]:
        element["review_state"] = "confirmed"
        if element["element_kind"] == "header_field" and (
            element["payload"]["name"] == "defects_recorded"
        ):
            element["review_state"] = "corrected"
            element["corrected_payload"] = {**element["payload"], "name": "defect_count"}
    draft_path.write_text(yaml.safe_dump(document, sort_keys=True))

    reviewed = runner.invoke(app, ["onboard", "review", proposal_id])
    assert "ready to approve" in reviewed.output, reviewed.output

    approved = runner.invoke(app, ["onboard", "approve", proposal_id,
                                   "--as", "synthetic.pdf.survey@v1", "--by", "rayno"])
    assert approved.exit_code == 0, approved.output
    assert "registered: SourceProfile synthetic.pdf.survey@v1" in approved.output


def _approve_transform(tmp_path) -> None:
    started = runner.invoke(app, [
        "map", "start", "--profile", "synthetic.pdf.survey@v1",
        "--template", "interim.defect_csv@1",
        "--exemplar", str(FIX / "survey_report_a.pdf"), "--no-ai",
    ])
    assert started.exit_code == 0, started.output
    session_id = re.search(r"session: (\d+)", started.output).group(1)
    draft = Path(re.search(r"draft:\s+(\S+)", started.output).group(1))

    for name, entries in [("survey_priority", PRIORITY), ("survey_defect", DEFECT),
                          ("survey_severity", SEVERITY)]:
        f = tmp_path / f"vm_{name}.yaml"
        f.write_text(yaml.safe_dump({"entries": entries}))
        assert runner.invoke(app, ["valuemap", "create", "--name", name,
                                   "--file", str(f)]).exit_code == 0

    doc = yaml.safe_load(draft.read_text())
    doc["routes"] = {
        "finding_id": {"from": "finding.ref", "tier": "T0"},
        "asset_name": {"from": "header.site", "tier": "T0"},
        "source_severity": {"from": "finding.class", "tier": "T1",
                            "value_map": {"name": "survey_severity", "version": 1}},
        "priority": {"from": "finding.class", "tier": "T1",
                     "value_map": {"name": "survey_priority", "version": 1}},
        "defect_code": {"from": "finding.class", "tier": "T1",
                        "value_map": {"name": "survey_defect", "version": 1}},
        "comments": {"from": "finding.observation", "tier": "T0"},
        "user_tags": {"from": "finding.component", "tier": "T0"},
        "source_page": {"from": "finding.sheet", "tier": "T0"},
    }
    doc["constants"] = {"inspection_method": "UAV visual",
                        "inspection_date": "2026-07-03"}
    doc["prompts"] = [{"key": "contract_number", "label": "contract", "required": True}]
    draft.write_text(yaml.safe_dump(doc, sort_keys=True))
    approved = runner.invoke(app, ["map", "approve", "--session", session_id,
                                   "--by", "rayno"])
    assert approved.exit_code == 0, approved.output


def test_onboard_map_apply_end_to_end(env):
    _onboard_and_approve(env)
    _approve_transform(env)

    # a DIFFERENT same-shape report auto-detects and converts, zero decisions
    batch = env / "batch"
    batch.mkdir()
    shutil.copy(FIX / "survey_report_b.pdf", batch)
    shutil.copy(FIX / "survey_report_drifted.pdf", batch)

    result = runner.invoke(app, ["apply", "run", str(batch),
                                 "--transform", "synthetic.pdf.survey@v1:interim.defect_csv@1",
                                 "--answer", "contract_number=E2E-003"])
    assert result.exit_code == 0, result.output
    assert "converted=1 blocked=1" in result.output  # b converts, drifted never does
    run_dir = Path(result.output.split("outputs: ")[1].splitlines()[0].strip())

    rows = list(csv.DictReader(
        (run_dir / "survey_report_b.defects.csv").open()
    ))
    assert len(rows) == 9  # every record in fixture B
    assert rows[0]["finding_id"] == "DF-001" and rows[0]["contract_number"] == "E2E-003"

    # drifted document: blocked AND pointed at seeded re-onboarding (FR-021)
    exceptions = (run_dir / "exceptions.csv").read_text()
    assert "survey_report_drifted.pdf" in exceptions
    assert "draft-profile" in exceptions


def test_misuse_and_skeleton_paths(env):
    warned = runner.invoke(app, ["onboard", "draft-profile",
                                 str(FIX / "target_form.pdf")])
    assert warned.exit_code == 1 and "draft-template" in warned.output  # FR-023

    prose = runner.invoke(app, ["onboard", "draft-profile",
                                str(FIX / "prose_report.pdf"), "--no-ai"])
    assert prose.exit_code == 0, prose.output  # FR-001b: skeleton, not failure
    assert "diagnosis" in prose.output and "hand" in prose.output


def test_seeded_reonboarding_reviews_as_a_delta(env):
    """T036 (FR-021): --seed-from annotates the proposal against the seeding
    recipe — matches carry seed_match evidence, divergences are flagged."""
    _onboard_and_approve(env)  # registers synthetic.pdf.survey@v1

    drafted = runner.invoke(app, ["onboard", "draft-profile",
                                  str(FIX / "survey_report_drifted.pdf"),
                                  "--seed-from", "synthetic.pdf.survey@v1", "--no-ai"])
    assert drafted.exit_code == 0, drafted.output
    draft_path = Path(re.search(r"draft: (\S+)", drafted.output).group(1))
    document = yaml.safe_load(draft_path.read_text())

    assert document["seeded_from"] == "synthetic.pdf.survey@v1"
    columns = {e["payload"]["name"]: e for e in document["elements"]
               if e["element_kind"] == "record_column"}
    assert columns["ref"]["evidence"]["seed_match"] is True
    assert "seed_divergent" not in columns["ref"].get("flags", [])
    # the drifted document renamed Class -> Category: a true delta finding
    assert columns["category"]["evidence"]["seed_match"] is False
    assert "seed_divergent" in columns["category"]["flags"]


def test_rejections_are_logged_for_follow_up(env):
    """T038 (FR-010): rejected onboarding attempts persist an occurrence."""
    import json

    from rmu.config import store_root

    rejected = runner.invoke(app, ["onboard", "draft-template",
                                   str(FIX / "target_encrypted.pdf")])
    assert rejected.exit_code == 1

    log = store_root() / "onboard_rejections.jsonl"
    assert log.exists()
    entry = json.loads(log.read_text().splitlines()[-1])
    assert "encrypted" in entry["condition"]
    assert entry["workaround"] and entry["at"]
    assert "target_encrypted.pdf" in entry["file"]
