"""T030 (SC-008): whole-exemplar local assist completes within the 5-minute
budget on the reference machine. Marked `slow`; auto-skips when the embedding
cache is absent so CI without assets stays green."""

import time

import pytest
from typer.testing import CliRunner

from rmu.ai.embeddings import EmbeddingBackend
from rmu.cli import app
from tests.conftest import block_non_loopback

runner = CliRunner()
EXEMPLAR = "seed/source_samples/Distribution-report.pdf"
MODEL = "BAAI/bge-small-en-v1.5"
BUDGET_SECONDS = 300

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not EmbeddingBackend(MODEL).available(),
        reason="bge-small cache not warmed (run `rmu ai setup`)",
    ),
]


def test_local_assist_within_five_minutes(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    monkeypatch.delenv("RMU_ASSIST_MODE", raising=False)
    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    assert runner.invoke(app, ["seed", "load"]).exit_code == 0

    start = time.monotonic()
    with block_non_loopback():
        result = runner.invoke(app, [
            "map", "start", "--profile", "scopito.pdf.powerline@v2020",
            "--template", "interim.defect_csv@1", "--exemplar", EXEMPLAR,
            "--assist", "local",
        ])
    elapsed = time.monotonic() - start
    assert result.exit_code == 0, result.output
    assert elapsed < BUDGET_SECONDS, f"local assist took {elapsed:.1f}s (>5min, SC-008)"
