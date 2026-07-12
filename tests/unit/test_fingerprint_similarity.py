"""T021 (FR-015): profile-fingerprint similarity suggests the resembling profile
and never touches apply-time detection."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from rmu.ai.embeddings import EmbeddingBackend
from rmu.cli import app

runner = CliRunner()
EXEMPLAR = "seed/source_samples/Distribution-report.pdf"
MODEL = "BAAI/bge-small-en-v1.5"

pytestmark = pytest.mark.skipif(
    not EmbeddingBackend(MODEL).available(),
    reason="bge-small cache not warmed (run `rmu ai setup`)",
)


def _bootstrap(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    assert runner.invoke(app, ["seed", "load"]).exit_code == 0


def test_suggest_ranks_the_known_profile(tmp_path, monkeypatch):
    _bootstrap(tmp_path, monkeypatch)
    result = runner.invoke(app, ["profile", "suggest", EXEMPLAR])
    assert result.exit_code == 0, result.output
    assert "resembles scopito.pdf.powerline@v2020" in result.output


def test_suggest_output_avoids_confidence_language(tmp_path, monkeypatch):
    _bootstrap(tmp_path, monkeypatch)
    result = runner.invoke(app, ["profile", "suggest", EXEMPLAR])
    # Principle V: framed as "resembles", never "match"/"confident".
    assert "resembles" in result.output
    assert "match" not in result.output.lower()


def test_suggest_is_read_only_direct(tmp_path, monkeypatch):
    # The suggest helper reads registry rows + leading text; it must not import
    # or mutate apply-time detection state. Smoke: detect_profile still works.
    _bootstrap(tmp_path, monkeypatch)
    from sqlalchemy import select

    from rmu.db import make_engine, make_session_factory
    from rmu.detect.fingerprint import detect_profile
    from rmu.models import SourceProfile

    engine = make_engine(f"sqlite:///{tmp_path}/rmu.db")
    with make_session_factory(engine)() as s:
        profiles = list(s.scalars(select(SourceProfile)))
    assert detect_profile(Path(EXEMPLAR), profiles) is not None
