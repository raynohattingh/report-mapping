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


def _stub_interpreter():
    """A StubAxisInterpreter targeting real (row, col) indices in
    matrix_target.pdf's grid (see test_matrix_reconstruct.py / the fixture's
    printed grid): row 2 = '4.2 Corrosion', col 3 = tower 'T2' — both already
    have deterministic axis entries for suggested_* to attach to."""
    from rmu.onboard.interpret_matrix import StubAxisInterpreter

    return StubAxisInterpreter({
        "row_axis": {
            "entries": [
                {"row": 2, "number": "4.2", "label": "Corrosion (AI)", "confidence": 0.9}
            ]
        },
        "col_axis": {
            "entries": [{"col": 3, "label": "Tower Two", "confidence": 0.8}]
        },
    })


def test_draft_template_wires_interpret_stage_for_matrix_targets(tmp_path, monkeypatch):
    """Fix 1 (005 final review): apply_interpretation/resolve_axis_interpreter
    had zero production callers — the AI interpret stage was unreachable from
    draft-template. Prove the wiring: a stubbed interpreter's suggestions
    land on the SAVED draft document's axis entries, and --no-ai yields none.
    """
    import rmu.onboard.drafting as drafting

    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    monkeypatch.setenv("RMU_PROFILES", str(tmp_path / "profiles"))
    assert runner.invoke(app, ["db", "init"]).exit_code == 0

    monkeypatch.setattr(drafting, "_axis_interpreter", lambda no_ai: _stub_interpreter())

    drafted = runner.invoke(app, ["onboard", "draft-template", FIXTURE])
    assert drafted.exit_code == 0, drafted.output
    draft_path = Path(re.search(r"draft: (\S+)", drafted.output).group(1))
    document = yaml.safe_load(draft_path.read_text())

    row_axis = next(e for e in document["elements"] if e["element_kind"] == "row_axis")
    col_axis = next(e for e in document["elements"] if e["element_kind"] == "col_axis")
    row_entry = next(e for e in row_axis["payload"]["entries"] if e["row"] == 2)
    col_entry = next(e for e in col_axis["payload"]["entries"] if e["col"] == 3)
    assert row_entry["suggested_label"] == "Corrosion (AI)"
    assert row_entry["suggested_number"] == "4.2"
    assert col_entry["suggested_label"] == "Tower Two"
    assert document["ai_assist"]["mode"] == "local"
    assert document["ai_assist"]["dropped"] == {
        "unknown_index": 0, "unmatched_axis_entry": 0,
    }


def test_draft_template_no_ai_skips_interpret_stage(tmp_path, monkeypatch):
    """--no-ai must yield no suggested_* hints and no ai_assist block, even
    with an interpreter available (the deterministic --no-ai floor)."""
    import rmu.onboard.drafting as drafting

    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    monkeypatch.setenv("RMU_PROFILES", str(tmp_path / "profiles"))
    assert runner.invoke(app, ["db", "init"]).exit_code == 0

    calls = []

    def _spy(no_ai):
        calls.append(no_ai)
        return _stub_interpreter() if not no_ai else None

    monkeypatch.setattr(drafting, "_axis_interpreter", _spy)

    drafted = runner.invoke(app, ["onboard", "draft-template", FIXTURE, "--no-ai"])
    assert drafted.exit_code == 0, drafted.output
    draft_path = Path(re.search(r"draft: (\S+)", drafted.output).group(1))
    document = yaml.safe_load(draft_path.read_text())

    assert "ai_assist" not in document
    for element in document["elements"]:
        if element["element_kind"] in ("row_axis", "col_axis"):
            for entry in element["payload"]["entries"]:
                assert "suggested_label" not in entry
    assert calls == [True]
