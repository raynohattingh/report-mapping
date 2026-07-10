"""T043 golden: the docx pack renders byte-identically to the committed
golden for fixed inputs (canonicalized OPC, research R1)."""

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rmu.cli import app
from rmu.render.docx import render_pack
from tests.golden.make_golden import PACK_CONTEXT
from tests.integration.helpers import (
    approve_annexc_transform,
    approve_defect_csv_transform,
)

runner = CliRunner()
GOLDEN = Path("tests/golden/data/expected_pack.docx")
TEMPLATE = Path("templates/interim.annexc_pack/pack_template.docx")


def test_pack_matches_golden_bytes():
    rendered = render_pack(TEMPLATE.read_bytes(), PACK_CONTEXT)
    assert rendered == GOLDEN.read_bytes(), (
        "docx pack rendering drifted from the committed golden; if intended, "
        "regenerate via tests/golden/make_golden.py and review the diff"
    )


@pytest.fixture()
def annexc_env(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    approve_defect_csv_transform(runner, tmp_path)
    approve_annexc_transform(runner, tmp_path)
    folder = tmp_path / "packs"
    folder.mkdir()
    shutil.copy("tests/fixtures/batch_20/synthetic_01.pdf", folder)
    shutil.copy("tests/fixtures/batch_20/synthetic_02.pdf", folder)
    return folder


def test_docx_batch_is_deterministic(annexc_env):
    """Second interim template end-to-end: pack outputs, byte-stable re-runs."""
    import hashlib

    hashes = []
    for _ in range(2):
        result = runner.invoke(app, [
            "apply", "run", str(annexc_env),
            "--transform", "scopito.pdf.powerline@v2020:interim.annexc_pack@1",
            "--answer", "contract_number=PACK-1",
        ])
        assert result.exit_code == 0, result.output
        run_dir = Path(result.output.split("outputs: ")[1].splitlines()[0].strip())
        packs = sorted(run_dir.glob("*.pack.docx"))
        assert len(packs) == 2
        hashes.append([hashlib.sha256(p.read_bytes()).hexdigest() for p in packs])
    assert hashes[0] == hashes[1]
