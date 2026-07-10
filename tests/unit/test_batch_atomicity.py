"""Analysis C4: an interrupted batch run leaves NO ApplyRun row — a partial
run is never mistakable for a completed one; re-running is always safe."""

import shutil

import pytest
from sqlalchemy import func, select
from typer.testing import CliRunner

import rmu.apply.batch as batch_mod
from rmu.apply.batch import BatchError, run_batch
from rmu.cli import app
from rmu.db import make_engine, make_session_factory
from rmu.models import ApplyRun, ConversionException

from tests.integration.helpers import approve_defect_csv_transform

runner = CliRunner()


@pytest.fixture()
def ready(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    approve_defect_csv_transform(runner, tmp_path)
    batch_dir = tmp_path / "batch"
    batch_dir.mkdir()
    shutil.copy("tests/fixtures/batch_20/synthetic_01.pdf", batch_dir)
    shutil.copy("tests/fixtures/batch_20/synthetic_02.pdf", batch_dir)
    engine = make_engine(f"sqlite:///{tmp_path}/rmu.db")
    return batch_dir, make_session_factory(engine)


def test_interrupted_run_records_nothing(ready, monkeypatch):
    batch_dir, factory = ready
    calls = {"n": 0}
    real = batch_mod.render_csv

    def explode_on_second(rows, columns):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("simulated mid-batch crash")
        return real(rows, columns)

    monkeypatch.setattr(batch_mod, "render_csv", explode_on_second)
    with factory() as s:
        with pytest.raises(RuntimeError, match="simulated"):
            run_batch(s, batch_dir, "scopito.pdf.powerline@v2020:interim.defect_csv@1",
                      {"contract_number": "X"}, "crash-test")
        s.rollback()
        assert s.scalar(select(func.count()).select_from(ApplyRun)) == 0
        assert s.scalar(select(func.count()).select_from(ConversionException)) == 0


def test_empty_batch_is_an_error_not_success(ready, tmp_path):
    _, factory = ready
    empty = tmp_path / "empty"
    empty.mkdir()
    with factory() as s:
        with pytest.raises(BatchError, match="empty batch"):
            run_batch(s, empty, "scopito.pdf.powerline@v2020:interim.defect_csv@1",
                      {"contract_number": "X"})
        assert s.scalar(select(func.count()).select_from(ApplyRun)) == 0
