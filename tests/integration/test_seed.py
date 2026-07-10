from sqlalchemy import func, select
from typer.testing import CliRunner

from rmu.cli import app
from rmu.db import make_engine, make_session_factory
from rmu.models import SourceProfile, TargetTemplate

runner = CliRunner()


def test_db_init_and_seed_load_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")

    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    first = runner.invoke(app, ["seed", "load"])
    assert first.exit_code == 0, first.output
    second = runner.invoke(app, ["seed", "load"])
    assert second.exit_code == 0, second.output

    engine = make_engine(f"sqlite:///{tmp_path}/rmu.db")
    with make_session_factory(engine)() as s:
        assert s.scalar(select(func.count()).select_from(SourceProfile)) == 1
        assert s.scalar(select(func.count()).select_from(TargetTemplate)) == 2
        for t in s.scalars(select(TargetTemplate)):
            assert t.interim is True  # SC-008: both shipped templates are INTERIM
            assert t.institution == "INTERIM"

    listed = runner.invoke(app, ["template", "list"])
    assert "interim.defect_csv@1" in listed.output
    assert "interim.annexc_pack@1" in listed.output
