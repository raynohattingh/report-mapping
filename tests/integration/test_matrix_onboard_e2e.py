"""T-006 e2e: a matrix (grid) target PDF onboards with row_axis/col_axis
elements, and approval attaches a `matrix` block to TargetTemplate.required_schema
alongside the existing flat `required` list, so apply/render/validate keep
working unchanged (feature 005)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from typer.testing import CliRunner

from rmu.cli import app
from rmu.db import make_engine, make_session_factory
from rmu.models import TargetTemplate

runner = CliRunner()
FIXTURE = "tests/fixtures/onboarding/matrix_target.pdf"


def test_matrix_template_registers_with_matrix_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    monkeypatch.setenv("RMU_PROFILES", str(tmp_path / "profiles"))
    assert runner.invoke(app, ["db", "init"]).exit_code == 0

    drafted = runner.invoke(app, ["onboard", "draft-template", FIXTURE, "--no-ai"])
    assert drafted.exit_code == 0, drafted.output
    pid = int(re.search(r"proposal: (\d+)", drafted.output).group(1))
    draft_path = Path(re.search(r"draft: (\S+)", drafted.output).group(1))

    # confirm every element (the CLI review flow is hand-editing the draft
    # YAML - see test_onboard_target_e2e.py::_onboard_template), then approve.
    document = yaml.safe_load(draft_path.read_text())
    for element in document["elements"]:
        element["review_state"] = "confirmed"
    draft_path.write_text(yaml.safe_dump(document, sort_keys=True))

    reviewed = runner.invoke(app, ["onboard", "review", str(pid)])
    assert reviewed.exit_code == 0, reviewed.output
    assert "ready to approve" in reviewed.output

    approved = runner.invoke(app, ["onboard", "approve", str(pid),
                                   "--name", "matrix.test@1", "--by", "tester"])
    assert approved.exit_code == 0, approved.output

    with make_session_factory(make_engine())() as s:
        row = s.query(TargetTemplate).filter_by(name="matrix.test").one()
    schema = row.required_schema
    assert "matrix" in schema
    assert {c["id"] for c in schema["matrix"]["criteria"]}  # criteria present
    assert {t["id"] for t in schema["matrix"]["towers"]}    # towers present
    assert schema["matrix"]["cell_field"] == "{criterion}__{tower}"
    assert all("__" in f for f in schema["required"])       # cell fields meaningful
