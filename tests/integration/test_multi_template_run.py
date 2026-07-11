"""T051: ONE batch run applies both interim templates — per source report the
manifest carries the report pack AND the defect CSV under a single ApplyRun,
and regeneration still hash-verifies (FR-014 / US2-AC1)."""

import shutil
from pathlib import Path

from sqlalchemy import select
from typer.testing import CliRunner

from rmu.cli import app
from rmu.db import make_engine, make_session_factory
from rmu.models import ApplyRun
from tests.integration.helpers import (
    approve_annexc_transform,
    approve_defect_csv_transform,
)

runner = CliRunner()
CSV_T = "scopito.pdf.powerline@v2020:interim.defect_csv@1"
PACK_T = "scopito.pdf.powerline@v2020:interim.annexc_pack@1"


def test_single_run_produces_both_outputs_per_report(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    approve_defect_csv_transform(runner, tmp_path)
    approve_annexc_transform(runner, tmp_path)

    folder = tmp_path / "batch"
    folder.mkdir()
    shutil.copy("tests/fixtures/batch_20/synthetic_01.pdf", folder)
    shutil.copy("tests/fixtures/batch_20/synthetic_02.pdf", folder)

    result = runner.invoke(app, [
        "apply", "run", str(folder),
        "--transform", CSV_T, "--transform", PACK_T,
        "--answer", "contract_number=BOTH-1", "--label", "both-templates",
    ])
    assert result.exit_code == 0, result.output
    run_dir = Path(result.output.split("outputs: ")[1].splitlines()[0].strip())

    # Per source report: defect CSV AND report pack (FR-014).
    for stem in ("synthetic_01", "synthetic_02"):
        assert (run_dir / f"{stem}.defects.csv").exists()
        assert (run_dir / f"{stem}.pack.docx").exists()

    engine = make_engine(f"sqlite:///{tmp_path}/rmu.db")
    with make_session_factory(engine)() as s:
        run = s.scalar(select(ApplyRun))
        assert len(run.transform_ids) == 2  # ONE audit record covers both
        kinds = {(m["document_sha"], m["output_kind"]) for m in run.outputs_manifest}
        assert len(kinds) == 4  # 2 docs x 2 output kinds
        run_id = run.id

    # Regen replays BOTH pinned transforms and hash-verifies all 4 outputs.
    regen = runner.invoke(app, ["apply", "regen", str(run_id)])
    assert regen.exit_code == 0, regen.output
    assert "4 outputs hash-verified" in regen.output
