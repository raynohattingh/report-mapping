"""T024 (FR-031, SC-002): studio approval runs the same gate, shows the same
refusals verbatim, stores the same Transform row, and can never double-register
after a racing CLI approval."""

from __future__ import annotations

import re

import yaml
from sqlalchemy import select
from typer.testing import CliRunner

from rmu.cli import app
from rmu.db import make_engine, make_session_factory
from rmu.models import MappingSession, Transform
from tests.studio.test_parity_foundation import complete_doc

runner = CliRunner()
EXEMPLAR = "seed/source_samples/Distribution-report.pdf"


def _start_manual() -> tuple[int, object]:
    from pathlib import Path

    started = runner.invoke(app, [
        "map", "start", "--profile", "scopito.pdf.powerline@v2020",
        "--template", "interim.defect_csv@1", "--exemplar", EXEMPLAR, "--no-ai",
    ])
    assert started.exit_code == 0, started.output
    session_id = int(re.search(r"session: (\d+)", started.output).group(1))
    draft = Path(re.search(r"draft:\s+(\S+)", started.output).group(1))
    return session_id, draft


def _complete(draft_path) -> None:
    doc = yaml.safe_load(draft_path.read_text())
    complete_doc(doc)
    draft_path.write_text(yaml.safe_dump(doc, sort_keys=True))


def test_refusal_reasons_shown_verbatim(studio_client, manual_session):
    session_id, _ = manual_session
    cli = runner.invoke(app, ["map", "approve", "--session", str(session_id),
                              "--by", "rayno"])
    assert cli.exit_code == 3
    cli_reasons = [line.strip("  - ") for line in cli.output.splitlines()
                   if line.startswith("  - ")]

    response = studio_client.post(f"/sessions/{session_id}/approve",
                                  data={"by": "rayno"})
    assert response.status_code == 422, response.text
    for reason in cli_reasons:
        assert reason in response.text.replace("&#39;", "'"), reason


def test_studio_approval_stores_same_transform_as_cli(studio_client, studio_env):
    cli_id, cli_draft = _start_manual()
    studio_id, studio_draft = _start_manual()
    _complete(cli_draft)
    _complete(studio_draft)
    assert cli_draft.read_bytes() == studio_draft.read_bytes()

    approved = runner.invoke(app, ["map", "approve", "--session", str(cli_id),
                                   "--by", "rayno"])
    assert approved.exit_code == 0, approved.output

    response = studio_client.post(f"/sessions/{studio_id}/approve",
                                  data={"by": "rayno"})
    assert response.status_code == 200, response.text

    with make_session_factory(make_engine())() as s:
        rows = list(s.scalars(select(Transform).order_by(Transform.version)))
        assert len(rows) == 2
        assert rows[0].yaml_body == rows[1].yaml_body  # identical stored text
        assert rows[1].parent_version == rows[0].version  # append-only lineage
        cli_ms = s.get(MappingSession, cli_id)
        studio_ms = s.get(MappingSession, studio_id)
        assert studio_ms.status == "approved"
        strip = lambda ds: [{k: v for k, v in d.items() if k != "at"}  # noqa: E731
                            for d in ds]
        assert strip(studio_ms.decisions) == strip(cli_ms.decisions)


def test_racing_approval_refused_never_double_registering(studio_client, studio_env):
    session_id, draft = _start_manual()
    _complete(draft)
    assert runner.invoke(app, ["map", "approve", "--session", str(session_id),
                               "--by", "rayno"]).exit_code == 0

    response = studio_client.post(f"/sessions/{session_id}/approve",
                                  data={"by": "rayno"})
    assert response.status_code == 422
    assert "terminal" in response.text or "approved" in response.text
    with make_session_factory(make_engine())() as s:
        assert len(list(s.scalars(select(Transform)))) == 1
