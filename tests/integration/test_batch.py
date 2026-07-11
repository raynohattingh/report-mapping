"""T034: zero-decision batch conversion of 20 same-shape reports (SC-002,
SC-006) — the 2 real Scopito PDFs + 18 committed synthetic fixtures."""

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rmu.cli import app
from tests.integration.helpers import approve_defect_csv_transform

runner = CliRunner()
TRANSFORM = "scopito.pdf.powerline@v2020:interim.defect_csv@1"


@pytest.fixture()
def batch_env(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    approve_defect_csv_transform(runner, tmp_path)
    folder = tmp_path / "batch_20"
    folder.mkdir()
    for pdf in Path("tests/fixtures/batch_20").glob("*.pdf"):
        shutil.copy(pdf, folder)
    for pdf in Path("seed/source_samples").glob("*.pdf"):
        shutil.copy(pdf, folder)
    assert len(list(folder.glob("*.pdf"))) == 20
    return folder


def test_batch_20_zero_field_decisions(batch_env):
    # Missing prompt answers fail fast, listing what is required (FR-011).
    missing = runner.invoke(app, ["apply", "run", str(batch_env),
                                  "--transform", TRANSFORM])
    assert missing.exit_code == 1
    assert "contract_number" in missing.output

    result = runner.invoke(app, ["apply", "run", str(batch_env),
                                 "--transform", TRANSFORM,
                                 "--answer", "contract_number=DEMO-001",
                                 "--label", "dod-batch"])
    assert result.exit_code == 0, result.output
    assert "converted=20 blocked=0" in result.output

    run_dir = Path(result.output.split("outputs: ")[1].strip())
    csvs = sorted(run_dir.glob("*.defects.csv"))
    assert len(csvs) == 20  # one defect CSV per source report (clarify #2)

    # Zero-findings fixture converts to a VALID empty output, not an error (C1).
    zero = run_dir / "synthetic_18_zero.defects.csv"
    lines = zero.read_text().strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith("finding_id,")

    # Exceptions report ALWAYS exists and carries the unmapped issue label
    # ('Lightning strike' deliberately absent from the value map) as oov_value
    # entries — reported, never guessed (US2 scenario 2; SC-006).
    exceptions = (run_dir / "exceptions.csv").read_text()
    assert "oov_value" in exceptions
    assert "Lightning strike" in exceptions

    # No guessed conversion anywhere: the failing label appears in NO output CSV.
    for csv_file in csvs:
        body = csv_file.read_text()
        assert "Lightning strike" not in body

    # Converted rows carry the prompt answer as a batch-level input.
    dist = (run_dir / "Distribution-report.defects.csv").read_text()
    assert "DEMO-001" in dist
    assert "P1" in dist  # severity 5 -> P1 via the pinned value map

    # Audit record exists and is inspectable.
    runs = runner.invoke(app, ["runs", "list"])
    assert "dod-batch" in runs.output


def test_duplicate_document_converted_once_and_noted(batch_env, tmp_path):
    """Spec edge case (convergence T053): duplicates detected by content
    fingerprint, converted once, the duplicate filename noted."""
    import json

    folder = tmp_path / "with_dup"
    folder.mkdir()
    src = Path("tests/fixtures/batch_20/synthetic_01.pdf")
    shutil.copy(src, folder / "synthetic_01.pdf")
    shutil.copy(src, folder / "zz_duplicate_of_01.pdf")  # same bytes, new name

    result = runner.invoke(app, ["apply", "run", str(folder),
                                 "--transform", TRANSFORM,
                                 "--answer", "contract_number=DUP-1"])
    assert result.exit_code == 0, result.output
    assert "documents=2 converted=1" in result.output
    run_dir = Path(result.output.split("outputs: ")[1].splitlines()[0].strip())

    # Converted exactly once — output exists for the first name only.
    assert (run_dir / "synthetic_01.defects.csv").exists()
    assert not (run_dir / "zz_duplicate_of_01.defects.csv").exists()

    # The duplicate filename is noted in the exceptions report and SafeCard.
    exceptions = (run_dir / "exceptions.csv").read_text()
    assert "zz_duplicate_of_01.pdf" in exceptions and "duplicate" in exceptions
    safecard = json.loads((run_dir / "safecard.json").read_text())
    by_doc = {d["document"]: d for d in safecard["documents"]}
    assert by_doc["zz_duplicate_of_01.pdf"]["blocked_kind"] == "duplicate"
    assert by_doc["synthetic_01.pdf"]["verdict"] in ("pass", "warn")
