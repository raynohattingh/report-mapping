"""T042: the weekend drift drill (SC-003) — batch_20 + both drifted fixtures
in ONE run: per-document quarantine verdicts, all 20 healthy documents
convert, blocked documents listed in the SafeCard batch summary and the
exceptions report."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rmu.cli import app
from tests.integration.helpers import approve_defect_csv_transform

runner = CliRunner()
TRANSFORM = "scopito.pdf.powerline@v2020:interim.defect_csv@1"


@pytest.fixture()
def drill_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    approve_defect_csv_transform(runner, tmp_path)
    folder = tmp_path / "drill"
    folder.mkdir()
    for pdf in Path("tests/fixtures/batch_20").glob("*.pdf"):
        shutil.copy(pdf, folder)
    for pdf in Path("seed/source_samples").glob("*.pdf"):
        shutil.copy(pdf, folder)
    for pdf in Path("tests/fixtures/drifted").glob("*.pdf"):
        shutil.copy(pdf, folder)
    assert len(list(folder.glob("*.pdf"))) == 22
    return folder


def test_drift_drill(drill_folder):
    result = runner.invoke(app, ["apply", "run", str(drill_folder),
                                 "--transform", TRANSFORM,
                                 "--answer", "contract_number=DRILL-1",
                                 "--label", "drift-drill"])
    assert result.exit_code == 0, result.output
    assert "documents=22 converted=20 blocked=2" in result.output
    run_dir = Path(result.output.split("outputs: ")[1].splitlines()[0].strip())

    # 20 healthy conversions, zero outputs for the drifted two.
    assert len(list(run_dir.glob("*.defects.csv"))) == 20
    assert not (run_dir / "drifted_header.defects.csv").exists()
    assert not (run_dir / "count_mismatch.defects.csv").exists()

    # SafeCard batch summary and exceptions report each list every block.
    safecard = json.loads((run_dir / "safecard.json").read_text())
    assert sorted(safecard["batch"]["blocked_documents"]) == [
        "count_mismatch.pdf", "drifted_header.pdf",
    ]
    assert safecard["batch"]["verdicts"]["block"] == 2
    assert safecard["batch"]["total"] == 22
    exceptions = (run_dir / "exceptions.csv").read_text()
    assert "drift_block" in exceptions and "unknown_profile" in exceptions

    # Zero drifted inputs mis-converted: every produced CSV came from a
    # healthy document (SC-003's sharp edge).
    produced = {p.name for p in run_dir.glob("*.defects.csv")}
    assert "drifted_header.defects.csv" not in produced
    assert "count_mismatch.defects.csv" not in produced
