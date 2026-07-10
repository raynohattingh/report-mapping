"""T041 — never cut (D3): any past run is exactly regenerable from its audit
record — inputs by fingerprint, recorded prompt answers, pinned transform and
template versions (FR-017/FR-018, SC-005)."""

import hashlib
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from rmu.cli import app
from tests.integration.helpers import approve_defect_csv_transform

runner = CliRunner()
TRANSFORM = "scopito.pdf.powerline@v2020:interim.defect_csv@1"


@pytest.fixture()
def completed_run(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    approve_defect_csv_transform(runner, tmp_path)
    folder = tmp_path / "batch"
    folder.mkdir()
    for pdf in list(Path("tests/fixtures/batch_20").glob("*.pdf"))[:5]:
        shutil.copy(pdf, folder)
    result = runner.invoke(app, ["apply", "run", str(folder), "--transform", TRANSFORM,
                                 "--answer", "contract_number=REGEN-1"])
    assert result.exit_code == 0, result.output
    run_id = int(result.output.split("run ")[1].split(":")[0])
    run_dir = Path(result.output.split("outputs: ")[1].splitlines()[0].strip())
    return run_id, run_dir, tmp_path


def test_regen_reproduces_manifest_exactly(completed_run):
    run_id, run_dir, tmp_path = completed_run
    regen = runner.invoke(app, ["apply", "regen", str(run_id)])
    assert regen.exit_code == 0, regen.output
    assert "hash-verified" in regen.output

    out_dir = Path(regen.output.split("outputs: ")[1].strip())
    # Independent byte-for-byte comparison of every conversion output.
    originals = {p.name: p.read_bytes() for p in run_dir.glob("*.defects.csv")}
    regenerated = {p.name: p.read_bytes() for p in out_dir.glob("*.defects.csv")}
    assert originals == regenerated
    assert len(originals) == 5


def test_regen_uses_pinned_transform_not_latest(completed_run):
    """A newer transform version must NOT change what regen produces."""
    run_id, run_dir, tmp_path = completed_run

    # Approve transform v2 with a different constant via a fresh session.
    started = runner.invoke(app, [
        "map", "start", "--profile", "scopito.pdf.powerline@v2020",
        "--template", "interim.defect_csv@1",
        "--exemplar", "seed/source_samples/Distribution-report.pdf", "--no-ai",
    ])
    import re
    session_id = int(re.search(r"session: (\d+)", started.output).group(1))
    draft_path = Path(re.search(r"draft:\s+(\S+)", started.output).group(1))
    # Reuse the v1 body but change a constant so v2 output would differ.
    from sqlalchemy import select

    from rmu.db import make_engine, make_session_factory
    from rmu.models import Transform as TransformModel
    engine = make_engine(f"sqlite:///{tmp_path}/rmu.db")
    with make_session_factory(engine)() as s:
        v1 = s.scalar(select(TransformModel).where(TransformModel.version == 1))
        doc = yaml.safe_load(v1.yaml_body)
    doc["constants"]["inspection_method"] = "CHANGED IN V2"
    draft_path.write_text(yaml.safe_dump(doc, sort_keys=True))
    approved = runner.invoke(app, ["map", "approve", "--session", str(session_id),
                                   "--by", "rayno"])
    assert approved.exit_code == 0, approved.output
    assert "transform v2" in approved.output

    regen = runner.invoke(app, ["apply", "regen", str(run_id)])
    assert regen.exit_code == 0, regen.output  # still verifies against v1 hashes
    out_dir = Path(regen.output.split("outputs: ")[1].strip())
    sample = hashlib.sha256(
        next(iter(sorted(out_dir.glob("*.defects.csv")))).read_bytes()
    ).hexdigest()
    original = hashlib.sha256(
        next(iter(sorted(run_dir.glob("*.defects.csv")))).read_bytes()
    ).hexdigest()
    assert sample == original
    assert "CHANGED IN V2" not in next(iter(sorted(out_dir.glob("*.defects.csv")))).read_text()
