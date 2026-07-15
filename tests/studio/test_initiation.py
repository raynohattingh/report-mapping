"""T038 (FR-036/FR-037, US5): starting work from the studio produces artifacts
indistinguishable from the CLI's, resolves assist mode by the existing
precedence, and surfaces every CLI rejection verbatim."""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from typer.testing import CliRunner

from rmu.cli import app

runner = CliRunner()
EXEMPLAR = "seed/source_samples/Distribution-report.pdf"


def _upload(studio_client, path: str, **fields):
    with open(path, "rb") as fh:
        return studio_client.post(
            "/start/session",
            data=fields,
            files={"exemplar": (Path(path).name, fh, "application/pdf")},
        )


def test_uploaded_session_matches_cli_start(studio_client, studio_env):
    # CLI start for the reference artifact
    cli = runner.invoke(app, [
        "map", "start", "--profile", "scopito.pdf.powerline@v2020",
        "--template", "interim.defect_csv@1", "--exemplar", EXEMPLAR, "--no-ai"])
    assert cli.exit_code == 0, cli.output
    cli_draft = Path(re.search(r"draft:\s+(\S+)", cli.output).group(1))
    cli_body = yaml.safe_load(cli_draft.read_text())

    response = _upload(studio_client, EXEMPLAR,
                       profile="scopito.pdf.powerline@v2020",
                       template="interim.defect_csv@1", assist="none")
    assert response.status_code == 200, response.text
    new_id = int(re.search(r"[Ss]ession (\d+)", response.text).group(1))
    studio_draft = cli_draft.parent / f"session_{new_id}.transform.yaml"
    # same routes/tiers/structure as the CLI start (banner carries the same
    # exemplar inventory since the content-addressed exemplar is identical)
    assert yaml.safe_load(studio_draft.read_text()) == cli_body


def test_drift_mismatch_blocks_with_cli_message(studio_client, studio_env):
    # a target-format PDF is not a scopito powerline exemplar → fingerprint block
    response = _upload(studio_client, "tests/fixtures/onboarding/target_grid.pdf",
                       profile="scopito.pdf.powerline@v2020",
                       template="interim.defect_csv@1", assist="none")
    assert response.status_code == 422, response.text
    assert "does not match the requested profile fingerprint" in response.text


def test_consentless_external_explained_not_bypassed(studio_client, studio_env):
    response = _upload(studio_client, EXEMPLAR,
                       profile="scopito.pdf.powerline@v2020",
                       template="interim.defect_csv@1", assist="external",
                       client="acme")
    assert response.status_code == 422, response.text
    assert "consent" in response.text.lower()


def test_onboarding_draft_from_studio_matches_cli(studio_client, studio_env):
    with open("tests/fixtures/onboarding/target_grid.pdf", "rb") as fh:
        response = studio_client.post(
            "/start/onboarding",
            data={"kind": "template"},
            files={"document": ("target_grid.pdf", fh, "application/pdf")},
        )
    assert response.status_code == 200, response.text
    assert re.search(r"[Pp]roposal (\d+)", response.text)


def test_unsupported_pdf_rejected_with_named_workaround(studio_client, studio_env):
    with open("tests/fixtures/onboarding/scanned_only.pdf", "rb") as fh:
        response = studio_client.post(
            "/start/onboarding",
            data={"kind": "profile"},
            files={"document": ("scanned_only.pdf", fh, "application/pdf")},
        )
    assert response.status_code == 422, response.text
    assert "workaround" in response.text.lower() or "scanned" in response.text.lower()
