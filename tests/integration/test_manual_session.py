"""T024: full manual --no-ai session on the Distribution exemplar (SC-007).

US1 acceptance scenarios 3/5/6: approval refused while unresolved; approved
Transform v1 stored with lineage; the whole flow needs zero AI availability.
"""

import re
from pathlib import Path

import yaml
from sqlalchemy import select
from typer.testing import CliRunner

from rmu.cli import app
from rmu.db import make_engine, make_session_factory
from rmu.models import (
    Base,  # noqa: F401  (ensures models are registered)
    MappingSession,
    Transform,
)

runner = CliRunner()
EXEMPLAR = "seed/source_samples/Distribution-report.pdf"


def _bootstrap(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    assert runner.invoke(app, ["seed", "load"]).exit_code == 0


def _complete_draft(draft_path: Path) -> None:
    """Simulate the analyst editing the draft: route every required field."""
    text = draft_path.read_text()
    doc = yaml.safe_load(text)
    doc["routes"] = {
        "finding_id": {"from": "finding.id", "tier": "T0"},
        "asset_name": {"from": "header.inspection_name", "tier": "T0"},
        "source_severity": {"from": "finding.severity", "tier": "T0"},
        "priority": {"from": "finding.severity", "tier": "T1",
                     "value_map": {"name": "severity_to_priority", "version": 1}},
        "defect_code": {"from": "finding.issues", "tier": "T1",
                        "value_map": {"name": "issue_to_defect_code", "version": 1}},
        "comments": {"from": "finding.comments", "tier": "T0"},
        "user_tags": {"from": "finding.user_tags", "tier": "T0"},
        "source_page": {"from": "finding.page", "tier": "T0"},
    }
    doc["constants"] = {"inspection_method": "UAV visual"}
    doc["formulas"] = {"inspection_date": {
        "fn": "date_format",
        "args": [{"field": "header.report_date"}, {"lit": "%Y-%m-%d"}],
    }}
    doc["prompts"] = [{"key": "contract_number", "label": "Client contract number",
                       "required": True}]
    draft_path.write_text(yaml.safe_dump(doc, sort_keys=True))


def _create_value_maps(tmp_path):
    sev = tmp_path / "sev.yaml"
    sev.write_text(yaml.safe_dump({"entries": [
        {"source_value": s, "target_value": t, "provenance": "human"}
        for s, t in [("1", "P4"), ("2", "P4"), ("3", "P3"), ("4", "P2"),
                     ("5", "P1"), ("?", "POI")]
    ]}))
    issues = tmp_path / "issues.yaml"
    issues.write_text(yaml.safe_dump({"entries": [
        {"source_value": s, "target_value": t, "provenance": "human"}
        for s, t in [("Conductor Damage", "C1"), ("Potential Hazard", "F1"),
                     ("Miscellaneous", "F12")]
    ]}))
    assert runner.invoke(app, ["valuemap", "create", "--name", "severity_to_priority",
                               "--file", str(sev)]).exit_code == 0
    assert runner.invoke(app, ["valuemap", "create", "--name", "issue_to_defect_code",
                               "--file", str(issues)]).exit_code == 0


def test_manual_session_end_to_end(tmp_path, monkeypatch):
    _bootstrap(tmp_path, monkeypatch)

    started = runner.invoke(app, [
        "map", "start", "--profile", "scopito.pdf.powerline@v2020",
        "--template", "interim.defect_csv@1", "--exemplar", EXEMPLAR, "--no-ai",
    ])
    assert started.exit_code == 0, started.output
    session_id = int(re.search(r"session: (\d+)", started.output).group(1))
    draft_path = Path(re.search(r"draft:\s+(\S+)", started.output).group(1))
    assert draft_path.exists()

    # Manual mode: zero proposals persisted, draft is all-T3 (scenario 6).
    draft = yaml.safe_load(draft_path.read_text())
    assert all(r["tier"] == "T3" for r in draft["routes"].values())

    # Scenario 3: approval refused while required fields are unresolved (exit 3).
    refused = runner.invoke(app, ["map", "approve", "--session", str(session_id),
                                  "--by", "rayno"])
    assert refused.exit_code == 3
    assert "unmapped" in refused.output or "T3" in refused.output

    _create_value_maps(tmp_path)
    _complete_draft(draft_path)

    # Scenario 4/FR-008: preview renders the exemplar through the draft.
    preview = runner.invoke(app, ["map", "preview", "--session", str(session_id)])
    assert preview.exit_code == 0, preview.output
    assert "rows=10" in preview.output
    assert "unresolved cells=0" in preview.output

    approved = runner.invoke(app, ["map", "approve", "--session", str(session_id),
                                   "--by", "rayno"])
    assert approved.exit_code == 0, approved.output
    assert "transform v1" in approved.output

    # Scenario 5: Transform v1 stored with approval metadata + session lineage.
    engine = make_engine(f"sqlite:///{tmp_path}/rmu.db")
    with make_session_factory(engine)() as s:
        transform = s.scalar(select(Transform))
        assert transform.version == 1
        assert transform.approved_by == "rayno"
        assert "severity_to_priority" in transform.yaml_body
        ms = s.scalar(select(MappingSession))
        assert ms.status == "approved"
        assert ms.mode == "manual"
        assert ms.proposals == []  # no AI involvement anywhere (SC-007)
        assert ms.resulting_transform_id == transform.id
        actions = {d["action"] for d in ms.decisions}
        assert actions == {"manual"}  # every decision human-authored, timestamped
        assert all(d["at"] for d in ms.decisions)
