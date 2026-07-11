"""T052: map preview renders the exemplar into its ACTUAL target format —
docx sessions produce a pack file, CSV sessions a CSV (FR-008)."""

import re
import zipfile
from pathlib import Path

from typer.testing import CliRunner

from rmu.cli import app
from tests.integration.helpers import (
    EXEMPLAR,
    approve_annexc_transform,
    approve_defect_csv_transform,
)

runner = CliRunner()


def test_preview_dispatches_on_template_kind(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    approve_defect_csv_transform(runner, tmp_path)   # session 1 (csv)
    approve_annexc_transform(runner, tmp_path)       # session 2 (docx)

    csv_preview = runner.invoke(app, ["map", "preview", "--session", "1"])
    assert csv_preview.exit_code == 0, csv_preview.output
    csv_path = Path(re.search(r"preview: (\S+)", csv_preview.output).group(1))
    assert csv_path.suffix == ".csv"
    assert csv_path.read_text().startswith("finding_id,")

    docx_preview = runner.invoke(app, ["map", "preview", "--session", "2"])
    assert docx_preview.exit_code == 0, docx_preview.output
    docx_path = Path(re.search(r"preview: (\S+)", docx_preview.output).group(1))
    assert docx_path.suffix == ".docx"
    assert zipfile.is_zipfile(docx_path)  # a real OPC pack, not a CSV stand-in
    assert "rows=10" in docx_preview.output


def test_new_session_preview_on_fresh_draft(tmp_path, monkeypatch):
    """Preview works pre-approval too: a fresh docx draft (all T3) previews
    with visible unresolved markers instead of failing."""
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    assert runner.invoke(app, ["seed", "load"]).exit_code == 0
    started = runner.invoke(app, [
        "map", "start", "--profile", "scopito.pdf.powerline@v2020",
        "--template", "interim.annexc_pack@1", "--exemplar", EXEMPLAR, "--no-ai",
    ])
    session_id = re.search(r"session: (\d+)", started.output).group(1)
    preview = runner.invoke(app, ["map", "preview", "--session", session_id])
    assert preview.exit_code == 0, preview.output
    assert ".preview.docx" in preview.output
    assert "unresolved cells=" in preview.output
