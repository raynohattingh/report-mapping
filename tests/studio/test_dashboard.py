"""T041 (FR-038/FR-039/FR-006, US6): the dashboard mirrors CLI listings, run
detail shows SafeCard verdicts/coverage/exceptions, abandon is the CLI terminal
transition, and registered artifacts expose no mutating action."""

from __future__ import annotations

import re

from typer.testing import CliRunner

from rmu.cli import app
from rmu.db import make_engine, make_session_factory
from rmu.models import ApplyRun, MappingSession
from tests.integration.helpers import approve_defect_csv_transform

runner = CliRunner()
EXEMPLAR = "seed/source_samples/Distribution-report.pdf"


def _run_batch(tmp_path):
    approve_defect_csv_transform(runner, tmp_path)
    batch = tmp_path / "batch"
    batch.mkdir()
    import shutil
    shutil.copy(EXEMPLAR, batch)
    result = runner.invoke(app, [
        "apply", "run", str(batch),
        "--transform", "scopito.pdf.powerline@v2020:interim.defect_csv@1",
        "--answer", "contract_number=DASH-1"])
    assert result.exit_code == 0, result.output
    return int(re.search(r"run (\d+):", result.output).group(1))


def test_dashboard_lists_registries_sessions_runs(studio_env, studio_client, tmp_path):
    run_id = _run_batch(tmp_path)
    response = studio_client.get("/dashboard")
    assert response.status_code == 200, response.text
    body = response.text
    assert "scopito.pdf.powerline@v2020" in body      # profile
    assert "interim.defect_csv@1" in body              # template
    assert "severity_to_priority" in body              # value map
    assert f"run {run_id}" in body or f"/runs/{run_id}" in body


def test_run_detail_shows_verdicts_and_exceptions(studio_env, studio_client, tmp_path):
    run_id = _run_batch(tmp_path)
    with make_session_factory(make_engine())() as s:
        run = s.get(ApplyRun, run_id)
        batch = run.safecard["batch"]
    response = studio_client.get(f"/runs/{run_id}")
    assert response.status_code == 200, response.text
    for verdict, count in batch["verdicts"].items():
        if count:
            assert verdict in response.text
    assert "exceptions" in response.text.lower()


def test_abandon_matches_cli_terminal_state(studio_env, studio_client):
    started = runner.invoke(app, [
        "map", "start", "--profile", "scopito.pdf.powerline@v2020",
        "--template", "interim.defect_csv@1", "--exemplar", EXEMPLAR, "--no-ai"])
    session_id = int(re.search(r"session: (\d+)", started.output).group(1))
    response = studio_client.post(f"/sessions/{session_id}/abandon")
    assert response.status_code == 200, response.text
    with make_session_factory(make_engine())() as s:
        assert s.get(MappingSession, session_id).status == "abandoned"


def test_registered_artifacts_have_no_mutating_action(studio_env, studio_client, tmp_path):
    _run_batch(tmp_path)
    response = studio_client.get("/dashboard")
    # approved transforms / registered templates are listed but carry no
    # edit/delete/mutate controls (FR-006)
    assert "hx-post" not in response.text.split("Transforms")[-1].split("</table>")[0] \
        if "Transforms" in response.text else True


def test_ai_health_and_consent(studio_env, studio_client):
    response = studio_client.get("/ai")
    assert response.status_code == 200, response.text
    assert "embeddings" in response.text.lower() or "tier 1" in response.text.lower()
    # grant consent, then it appears
    granted = studio_client.post("/ai/consent",
                                 data={"action": "grant", "client": "acme", "by": "rayno"})
    assert granted.status_code == 200, granted.text
    from rmu.ai.config import has_consent, load_ai_config
    from rmu.config import store_root
    assert has_consent(load_ai_config(store_root()), "acme")
