"""T022 (SC-005/006, FR-003/004/009): owner-controlled assistance modes.

External mode refuses without recorded per-client consent; `none`/`--no-ai`
run end to end; and stored artifacts are structurally identical across modes.
No real network is ever used (external is refused before any provider runs).
"""

import re
from pathlib import Path

import yaml
from typer.testing import CliRunner

from rmu.cli import app

runner = CliRunner()
EXEMPLAR = "seed/source_samples/Distribution-report.pdf"


def _bootstrap(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    monkeypatch.delenv("RMU_ASSIST_MODE", raising=False)
    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    assert runner.invoke(app, ["seed", "load"]).exit_code == 0


def _start(mode_args):
    return runner.invoke(app, [
        "map", "start", "--profile", "scopito.pdf.powerline@v2020",
        "--template", "interim.defect_csv@1", "--exemplar", EXEMPLAR, *mode_args,
    ])


def _draft_keys(output):
    draft_path = Path(re.search(r"draft:\s+(\S+)", output).group(1))
    return set(yaml.safe_load(draft_path.read_text()))


def test_external_without_client_refused(tmp_path, monkeypatch):
    _bootstrap(tmp_path, monkeypatch)
    result = _start(["--assist", "external"])
    assert result.exit_code == 4
    assert "client" in result.output.lower()


def test_external_without_consent_refused(tmp_path, monkeypatch):
    _bootstrap(tmp_path, monkeypatch)
    result = _start(["--assist", "external", "--client", "acme"])
    assert result.exit_code == 4
    assert "consent" in result.output.lower()


def test_consent_is_per_client(tmp_path, monkeypatch):
    _bootstrap(tmp_path, monkeypatch)
    assert runner.invoke(app, ["ai", "consent", "grant", "--client", "acme",
                               "--by", "rayno"]).exit_code == 0
    # Consent for acme does not authorize a different client.
    other = _start(["--assist", "external", "--client", "globex"])
    assert other.exit_code == 4
    # acme is now allowed past the gate (it then tries the real provider, which
    # we never reach here because there is no API key/network — but the refusal
    # gate must NOT fire for acme).
    allowed = _start(["--assist", "external", "--client", "acme"])
    assert "no external-API consent" not in allowed.output


def test_none_mode_fully_functional(tmp_path, monkeypatch):
    _bootstrap(tmp_path, monkeypatch)
    result = _start(["--assist", "none"])
    assert result.exit_code == 0, result.output
    assert "mode=manual" in result.output


def test_no_ai_is_alias_for_none(tmp_path, monkeypatch):
    _bootstrap(tmp_path, monkeypatch)
    result = _start(["--no-ai"])
    assert result.exit_code == 0, result.output
    assert "mode=manual" in result.output


def test_artifact_shape_identical_across_modes(tmp_path, monkeypatch):
    # SC-006/FR-009: draft transform structure is identical whether produced by a
    # manual session or an assisted (stub) one.
    _bootstrap(tmp_path, monkeypatch)
    manual_keys = _draft_keys(_start(["--no-ai"]).output)
    stub_keys = _draft_keys(_start(["--stub-ai"]).output)
    assert manual_keys == stub_keys
    assert manual_keys == {"meta", "routes", "constants", "formulas", "prompts", "exceptions"}
