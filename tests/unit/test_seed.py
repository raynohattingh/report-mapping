"""Seed loading must accept onboarded recipe YAMLs (regression).

`onboard approve` writes recipes with a quoted ISO `effective_from` (a YAML
string); hand-authored seed YAMLs parse as dates. `seed load` globs both from
profiles/ and must load either — a registered profile breaking every later
`seed load` (and half the test suite in a real checkout) is a latent bug.
"""

from __future__ import annotations

import datetime

import yaml
from sqlalchemy import select
from typer.testing import CliRunner

from rmu.cli import app
from rmu.db import make_engine, make_session_factory
from rmu.models import SourceProfile

runner = CliRunner()

ONBOARDED_RECIPE = {
    "key": "synthetic.pdf.onboarded",
    "structural_version": "v1",
    "platform": "synthetic",
    "export_kind": "pdf",
    "job_type": "onboarded",
    "extractor_ref": "rmu.extract.recipe_pdf",
    "effective_from": "2026-07-13",  # str, exactly as approve.py writes it
    "fingerprint": {"required_text": ["Defect register"]},
    "records": {
        "detection": {"mode": "column_clusters", "row_pattern": r"^\S+$"},
        "columns": [{"name": "ref"}],
    },
}


def test_seed_load_accepts_onboarded_recipe_with_string_date(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    monkeypatch.setenv("RMU_PROFILES", str(tmp_path / "profiles"))
    (tmp_path / "profiles").mkdir()
    (tmp_path / "profiles" / "synthetic.pdf.onboarded.v1.yaml").write_text(
        yaml.safe_dump(ONBOARDED_RECIPE, sort_keys=True)
    )

    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    result = runner.invoke(app, ["seed", "load"])
    assert result.exit_code == 0, result.output

    with make_session_factory(make_engine())() as s:
        row = s.scalar(
            select(SourceProfile).where(SourceProfile.key == "synthetic.pdf.onboarded")
        )
        assert row is not None
        assert row.effective_from == datetime.date(2026, 7, 13)
