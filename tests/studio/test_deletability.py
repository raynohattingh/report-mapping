"""FR-042 / SC-004: the studio is a deletable subpackage (feature 004, D11).

`rmu studio` must work when the studio group is installed, exit with an
actionable hint when it is not, and its absence must leave every other CLI
command untouched. The suite-wide half of SC-004 (full suite green without the
group) is the module-wide importorskip in conftest.py plus the deletion drill
(T045).
"""

from __future__ import annotations

import builtins

from typer.testing import CliRunner

from rmu.cli import app

runner = CliRunner()


def test_studio_command_registered_and_help_works():
    result = runner.invoke(app, ["studio", "--help"])
    assert result.exit_code == 0, result.output
    assert "--no-browser" in result.output
    assert "--port" in result.output


def test_studio_command_absent_group_exits_with_hint(monkeypatch):
    """Simulate the core-only install: importing rmu.studio.launch fails."""
    real_import = builtins.__import__

    def failing_import(name, *args, **kwargs):
        if name.startswith("rmu.studio") or name in ("fastapi", "uvicorn"):
            raise ModuleNotFoundError(f"No module named '{name}'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", failing_import)
    result = runner.invoke(app, ["studio", "--no-browser"])
    assert result.exit_code != 0
    assert "uv sync --group studio" in result.output


def test_other_cli_commands_unaffected_by_studio_absence(monkeypatch):
    real_import = builtins.__import__

    def failing_import(name, *args, **kwargs):
        if name.startswith("rmu.studio"):
            raise ModuleNotFoundError(f"No module named '{name}'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", failing_import)
    assert runner.invoke(app, ["--help"]).exit_code == 0
    assert runner.invoke(app, ["profile", "--help"]).exit_code == 0
    assert runner.invoke(app, ["map", "--help"]).exit_code == 0


def test_full_mapping_and_apply_cycle_with_studio_absent(tmp_path, monkeypatch):
    """T045/SC-004: with rmu.studio unimportable, a whole map→approve→apply
    cycle still works — every CLI capability remains intact."""
    import re
    import shutil
    from pathlib import Path

    import yaml

    monkeypatch.setenv("RMU_STORE", str(tmp_path))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    monkeypatch.setenv("RMU_PROFILES", str(tmp_path / "profiles"))

    real_import = builtins.__import__

    def failing_import(name, *args, **kwargs):
        if name.startswith("rmu.studio"):
            raise ModuleNotFoundError("studio package removed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", failing_import)

    exemplar = "seed/source_samples/Distribution-report.pdf"
    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    assert runner.invoke(app, ["seed", "load"]).exit_code == 0
    started = runner.invoke(app, [
        "map", "start", "--profile", "scopito.pdf.powerline@v2020",
        "--template", "interim.defect_csv@1", "--exemplar", exemplar, "--no-ai"])
    assert started.exit_code == 0, started.output
    session_id = re.search(r"session: (\d+)", started.output).group(1)
    draft = Path(re.search(r"draft:\s+(\S+)", started.output).group(1))

    for name, entries in [("severity_to_priority",
                           [{"source_value": s, "target_value": t, "provenance": "human"}
                            for s, t in [("1", "P4"), ("2", "P4"), ("3", "P3"),
                                         ("4", "P2"), ("5", "P1"), ("?", "POI")]]),
                          ("issue_to_defect_code",
                           [{"source_value": s, "target_value": t, "provenance": "human"}
                            for s, t in [("Conductor Damage", "C1"),
                                         ("Potential Hazard", "F1"),
                                         ("Miscellaneous", "F12"), ("Corrosion", "A3")]])]:
        f = tmp_path / f"vm_{name}.yaml"
        f.write_text(yaml.safe_dump({"entries": entries}))
        assert runner.invoke(app, ["valuemap", "create", "--name", name,
                                   "--file", str(f)]).exit_code == 0

    doc = yaml.safe_load(draft.read_text())
    doc["routes"] = {
        "finding_id": {"from": "finding.id", "tier": "T0"},
        "asset_name": {"from": "header.inspection_name", "tier": "T0"},
        "source_severity": {"from": "finding.severity", "tier": "T0"},
        "priority": {"from": "finding.severity", "tier": "T1",
                     "value_map": {"name": "severity_to_priority", "version": 1}},
        "defect_code": {"from": "finding.issues", "tier": "T1",
                        "value_map": {"name": "issue_to_defect_code", "version": 1}},
    }
    doc["constants"] = {"inspection_method": "UAV visual"}
    doc["formulas"] = {"inspection_date": {
        "fn": "date_format",
        "args": [{"field": "header.report_date"}, {"lit": "%Y-%m-%d"}]}}
    doc["prompts"] = [{"key": "contract_number", "label": "Contract", "required": True}]
    draft.write_text(yaml.safe_dump(doc, sort_keys=True))
    assert runner.invoke(app, ["map", "approve", "--session", session_id,
                               "--by", "rayno"]).exit_code == 0

    batch = tmp_path / "batch"
    batch.mkdir()
    shutil.copy(exemplar, batch)
    result = runner.invoke(app, [
        "apply", "run", str(batch),
        "--transform", "scopito.pdf.powerline@v2020:interim.defect_csv@1",
        "--answer", "contract_number=NOSTUDIO"])
    assert result.exit_code == 0, result.output
    assert "converted=1" in result.output
