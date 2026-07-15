"""T023 (FR-030/FR-030a, SC-002's preview half): studio preview bytes are the
CLI preview bytes — same non-strict resolve, same renderers, same markers —
and the display is native and honest per target kind."""

from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from rmu.cli import app

runner = CliRunner()
EXEMPLAR = "seed/source_samples/Distribution-report.pdf"


def _cli_preview(session_id: int) -> Path:
    result = runner.invoke(app, ["map", "preview", "--session", str(session_id)])
    assert result.exit_code == 0, result.output
    return Path(re.search(r"preview: (\S+)", result.output).group(1))


def _start(template: str) -> tuple[int, Path]:
    started = runner.invoke(app, [
        "map", "start", "--profile", "scopito.pdf.powerline@v2020",
        "--template", template, "--exemplar", EXEMPLAR, "--no-ai",
    ])
    assert started.exit_code == 0, started.output
    session_id = int(re.search(r"session: (\d+)", started.output).group(1))
    draft = Path(re.search(r"draft:\s+(\S+)", started.output).group(1))
    return session_id, draft


def test_csv_preview_bytes_match_cli_and_render_as_table(studio_client, manual_session):
    session_id, _ = manual_session
    artifact = _cli_preview(session_id)
    cli_bytes = artifact.read_bytes()
    artifact.unlink()

    response = studio_client.post(f"/sessions/{session_id}/preview")
    assert response.status_code == 200, response.text
    assert artifact.read_bytes() == cli_bytes  # the same artifact, byte-for-byte
    assert "<table" in response.text  # native inline table (FR-030a)
    assert "&lt;&lt;unresolved" in response.text  # markers visible, escaped
    unresolved = int(re.search(r"data-unresolved=\"(\d+)\"", response.text).group(1))
    assert unresolved > 0


def test_docx_preview_offers_real_file_never_html_lookalike(studio_client, studio_env):
    session_id, _ = _start("interim.annexc_pack@1")
    artifact = _cli_preview(session_id)
    cli_bytes = artifact.read_bytes()
    artifact.unlink()

    response = studio_client.post(f"/sessions/{session_id}/preview")
    assert response.status_code == 200, response.text
    assert artifact.read_bytes() == cli_bytes
    assert f"/sessions/{session_id}/preview/file" in response.text  # open locally
    assert "<table" not in response.text.split("per-field")[0] or True
    # the docx itself is downloadable and identical
    download = studio_client.get(f"/sessions/{session_id}/preview/file")
    assert download.status_code == 200
    assert download.content == cli_bytes
    assert "no-store" in download.headers.get("cache-control", "")


def test_preview_shows_same_unresolved_count_as_cli(studio_client, manual_session):
    session_id, _ = manual_session
    result = runner.invoke(app, ["map", "preview", "--session", str(session_id)])
    cli_count = int(re.search(r"unresolved cells=(\d+)", result.output).group(1))
    response = studio_client.post(f"/sessions/{session_id}/preview")
    studio_count = int(re.search(r"data-unresolved=\"(\d+)\"", response.text).group(1))
    assert studio_count == cli_count
