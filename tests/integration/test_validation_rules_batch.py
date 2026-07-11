"""T050 batch-level: a value-map target OUTSIDE the template's registered
vocabulary surfaces as an invalid_value exception and the row never ships —
the semantically-wrong-but-structurally-valid guard (Constitution V spirit)."""

import shutil
from pathlib import Path

from typer.testing import CliRunner

from rmu.cli import app
from tests.integration.helpers import approve_defect_csv_transform

runner = CliRunner()
TRANSFORM = "scopito.pdf.powerline@v2020:interim.defect_csv@1"

# A human mistake at mapping time: 'Conductor Damage' mapped to a code that is
# NOT in seed/defect_codes_v1.csv. Structurally valid; semantically wrong.
BAD_ISSUE_ENTRIES = [
    {"source_value": "Conductor Damage", "target_value": "ZZZ", "provenance": "human"},
    {"source_value": "Potential Hazard", "target_value": "F1", "provenance": "human"},
    {"source_value": "Miscellaneous", "target_value": "F12", "provenance": "human"},
]


def test_vocabulary_illegal_target_is_reported_never_shipped(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    approve_defect_csv_transform(runner, tmp_path, issue_entries=BAD_ISSUE_ENTRIES)

    folder = tmp_path / "batch"
    folder.mkdir()
    shutil.copy("seed/source_samples/Distribution-report.pdf", folder)

    result = runner.invoke(app, ["apply", "run", str(folder), "--transform", TRANSFORM,
                                 "--answer", "contract_number=X"])
    assert result.exit_code == 0, result.output
    run_dir = Path(result.output.split("outputs: ")[1].splitlines()[0].strip())

    # ZZZ appears in NO output; the affected records are exceptions instead.
    output = (run_dir / "Distribution-report.defects.csv").read_text()
    assert "ZZZ" not in output
    exceptions = (run_dir / "exceptions.csv").read_text()
    assert "invalid_value" in exceptions
    assert "ZZZ" in exceptions
    assert "vocabulary" in exceptions
    # Healthy records (Potential Hazard/Miscellaneous routes) still converted.
    assert "F12" in output or "F1" in output
