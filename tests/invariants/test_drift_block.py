"""T036 — never cut (D3): drifted/unknown documents are individually
quarantined with NO output while healthy documents in the same batch convert
(FR-016, SC-003, clarify 2026-07-10)."""

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
def mixed_batch(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    approve_defect_csv_transform(runner, tmp_path)
    folder = tmp_path / "mixed"
    folder.mkdir()
    shutil.copy("tests/fixtures/batch_20/synthetic_01.pdf", folder)
    shutil.copy("tests/fixtures/drifted/drifted_header.pdf", folder)
    shutil.copy("tests/fixtures/drifted/count_mismatch.pdf", folder)
    return folder


def test_drifted_documents_blocked_healthy_converts(mixed_batch):
    result = runner.invoke(app, ["apply", "run", str(mixed_batch),
                                 "--transform", TRANSFORM,
                                 "--answer", "contract_number=X"])
    assert result.exit_code == 0, result.output  # healthy doc converted
    assert "converted=1 blocked=2" in result.output
    run_dir = Path(result.output.split("outputs: ")[1].splitlines()[0].strip())

    # Healthy document converted; NO output of any kind for the drifted two.
    assert (run_dir / "synthetic_01.defects.csv").exists()
    assert not (run_dir / "drifted_header.defects.csv").exists()
    assert not (run_dir / "count_mismatch.defects.csv").exists()

    # Both blocked documents listed in the SafeCard batch summary (FR-016).
    safecard = json.loads((run_dir / "safecard.json").read_text())
    assert sorted(safecard["batch"]["blocked_documents"]) == [
        "count_mismatch.pdf", "drifted_header.pdf",
    ]
    by_doc = {d["document"]: d for d in safecard["documents"]}
    assert by_doc["drifted_header.pdf"]["blocked_kind"] == "unknown_profile"
    assert by_doc["count_mismatch.pdf"]["blocked_kind"] == "drift_block"
    assert "declares 10" in by_doc["count_mismatch.pdf"]["reason"]
    assert by_doc["synthetic_01.pdf"]["verdict"] in ("pass", "warn")

    # And in the exceptions report, with human-review routing suggestions.
    exceptions = (run_dir / "exceptions.csv").read_text()
    assert "drifted_header.pdf" in exceptions and "unknown_profile" in exceptions
    assert "count_mismatch.pdf" in exceptions and "drift_block" in exceptions
    # FR-021 (feature 003): the block now points at seeded re-onboarding
    assert "draft-profile" in exceptions


def test_all_blocked_batch_signals_blocked_exit(mixed_batch, tmp_path):
    only_drifted = tmp_path / "only_drifted"
    only_drifted.mkdir()
    shutil.copy("tests/fixtures/drifted/count_mismatch.pdf", only_drifted)
    result = runner.invoke(app, ["apply", "run", str(only_drifted),
                                 "--transform", TRANSFORM,
                                 "--answer", "contract_number=X"])
    assert result.exit_code == 2  # distinct 'blocked' signal (spec A1 remediation)
