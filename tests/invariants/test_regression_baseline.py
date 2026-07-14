"""T003 (003-pdf-format-onboarding) — SC-007 regression baseline.

Byte-hashes of the CURRENT scopito v2020 extraction + both interim template
renders on the seed Distribution exemplar, captured BEFORE any 003 feature code
(research R10). The feature must never change these outputs (FR-019).

Capture/refresh (only legitimate when main's behaviour intentionally changes):
    RMU_CAPTURE_SC007=1 uv run pytest tests/invariants/test_regression_baseline.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rmu.cli import app
from tests.integration.helpers import (
    approve_annexc_transform,
    approve_defect_csv_transform,
)

runner = CliRunner()
BASELINE = Path("tests/invariants/baselines/sc007_baseline.json")
EXEMPLAR = Path("seed/source_samples/Distribution-report.pdf")


def _hash_run_dir(run_dir: Path) -> dict[str, str]:
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(run_dir.iterdir())
        if p.is_file()
    }


def _apply(batch_dir: Path, transform: str) -> Path:
    result = runner.invoke(
        app,
        ["apply", "run", str(batch_dir), "--transform", transform,
         "--answer", "contract_number=SC007-BASELINE"],
    )
    assert result.exit_code == 0, result.output
    return Path(result.output.split("outputs: ")[1].splitlines()[0].strip())


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    approve_defect_csv_transform(runner, tmp_path)
    approve_annexc_transform(runner, tmp_path)
    batch = tmp_path / "batch"
    batch.mkdir()
    shutil.copy(EXEMPLAR, batch)
    return batch


def test_scopito_and_interim_outputs_match_pre_003_baseline(env):
    current = {
        "interim.defect_csv@1": _hash_run_dir(
            _apply(env, "scopito.pdf.powerline@v2020:interim.defect_csv@1")
        ),
        "interim.annexc_pack@1": _hash_run_dir(
            _apply(env, "scopito.pdf.powerline@v2020:interim.annexc_pack@1")
        ),
    }

    if os.environ.get("RMU_CAPTURE_SC007"):
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
        pytest.skip(f"baseline captured to {BASELINE}")

    assert BASELINE.exists(), (
        "SC-007 baseline missing — capture it on a pre-003 tree with "
        "RMU_CAPTURE_SC007=1 before making feature changes"
    )
    baseline = json.loads(BASELINE.read_text())
    assert current == baseline, (
        "003 changed existing scopito/interim output bytes — forbidden by FR-019/SC-007"
    )
