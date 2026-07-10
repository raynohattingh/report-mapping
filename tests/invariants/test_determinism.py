"""T038 — never cut (D3): byte-identical re-runs, proven by straight file
hashes. Outputs embed NO generation timestamps (FR-011, SC-004, research R1)."""

import hashlib
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rmu.cli import app
from tests.integration.helpers import approve_defect_csv_transform

runner = CliRunner()
TRANSFORM = "scopito.pdf.powerline@v2020:interim.defect_csv@1"


def _hash_dir(run_dir: Path) -> dict[str, str]:
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(run_dir.iterdir())
        if p.is_file()
    }


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    approve_defect_csv_transform(runner, tmp_path)
    folder = tmp_path / "batch"
    folder.mkdir()
    for pdf in list(Path("tests/fixtures/batch_20").glob("*.pdf"))[:6]:
        shutil.copy(pdf, folder)
    shutil.copy("seed/source_samples/Distribution-report.pdf", folder)
    return folder


def test_identical_rerun_is_byte_identical(env):
    hashes = []
    for _ in range(2):
        result = runner.invoke(app, ["apply", "run", str(env),
                                     "--transform", TRANSFORM,
                                     "--answer", "contract_number=DEMO-001"])
        assert result.exit_code == 0, result.output
        run_dir = Path(result.output.split("outputs: ")[1].splitlines()[0].strip())
        hashes.append(_hash_dir(run_dir))
    # STRAIGHT hash comparison of every output artifact — outputs, exceptions
    # report and SafeCard alike. No masking, nowhere for drift to hide.
    assert hashes[0] == hashes[1]


def test_prompt_answers_are_part_of_the_inputs(env):
    """Different batch-level inputs may change content — same inputs must not."""
    outs = []
    for answer in ["contract_number=A", "contract_number=B"]:
        result = runner.invoke(app, ["apply", "run", str(env),
                                     "--transform", TRANSFORM, "--answer", answer])
        run_dir = Path(result.output.split("outputs: ")[1].splitlines()[0].strip())
        outs.append((run_dir / "Distribution-report.defects.csv").read_text())
    assert "A" in outs[0] and "B" in outs[1]
    assert outs[0] != outs[1]
