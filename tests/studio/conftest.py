"""Studio test fixtures (feature 004).

The whole directory skips when the optional `studio` dependency group is not
installed (FR-042/SC-004: absence is a first-class state, and the rest of the
suite must be green without it).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="studio dependency group not installed (D11)")

from typer.testing import CliRunner  # noqa: E402

EXEMPLAR = "seed/source_samples/Distribution-report.pdf"
TOKEN = "test-launch-token-0123456789abcdef"
PORT = 8765
LOOPBACK = ("127.0.0.1", 55555)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def studio_env(tmp_path, monkeypatch, runner):
    """Isolated store + seeded DB, same bootstrap the integration tests use."""
    from rmu.cli import app

    monkeypatch.setenv("RMU_STORE", str(tmp_path))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    monkeypatch.setenv("RMU_PROFILES", str(tmp_path / "profiles"))
    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    assert runner.invoke(app, ["seed", "load"]).exit_code == 0
    return tmp_path


@pytest.fixture
def manual_session(studio_env, runner):
    """A draft --no-ai mapping session on the seed exemplar (defect CSV target)."""
    from rmu.cli import app

    started = runner.invoke(app, [
        "map", "start", "--profile", "scopito.pdf.powerline@v2020",
        "--template", "interim.defect_csv@1", "--exemplar", EXEMPLAR, "--no-ai",
    ])
    assert started.exit_code == 0, started.output
    session_id = int(re.search(r"session: (\d+)", started.output).group(1))
    draft_path = Path(re.search(r"draft:\s+(\S+)", started.output).group(1))
    return session_id, draft_path


@pytest.fixture
def stub_session(studio_env, runner):
    """A draft session with canned T2 proposals (deterministic StubProvider)."""
    from rmu.cli import app

    started = runner.invoke(app, [
        "map", "start", "--profile", "scopito.pdf.powerline@v2020",
        "--template", "interim.defect_csv@1", "--exemplar", EXEMPLAR, "--stub-ai",
    ])
    assert started.exit_code == 0, started.output
    session_id = int(re.search(r"session: (\d+)", started.output).group(1))
    draft_path = Path(re.search(r"draft:\s+(\S+)", started.output).group(1))
    return session_id, draft_path


@pytest.fixture
def template_proposal(studio_env, runner):
    """A draft pdf_overlay template proposal (11 grid regions + cardinality)."""
    from rmu.cli import app

    drafted = runner.invoke(app, ["onboard", "draft-template",
                                  "tests/fixtures/onboarding/target_grid.pdf"])
    assert drafted.exit_code == 0, drafted.output
    proposal_id = int(re.search(r"proposal: (\d+)", drafted.output).group(1))
    draft_path = Path(re.search(r"draft: (\S+)", drafted.output).group(1))
    return proposal_id, draft_path


@pytest.fixture
def matrix_proposal(studio_env, runner):
    """A draft template proposal on the criteria x tower grid fixture (3
    criteria 4.1/4.2/4.3, 3 towers T1/T2/T3, 9 cells) — feature 006's matrix
    projection input. Mirrors `template_proposal` exactly, pointed at
    matrix_target.pdf, --no-ai (no interpret-stage suggestions)."""
    from rmu.cli import app

    drafted = runner.invoke(app, ["onboard", "draft-template",
                                  "tests/fixtures/onboarding/matrix_target.pdf",
                                  "--no-ai"])
    assert drafted.exit_code == 0, drafted.output
    proposal_id = int(re.search(r"proposal: (\d+)", drafted.output).group(1))
    draft_path = Path(re.search(r"draft: (\S+)", drafted.output).group(1))
    return proposal_id, draft_path


@pytest.fixture
def no_grid_proposal(studio_env, runner):
    """A draft template proposal with NO grid (pdf_form) — no row_axis/col_axis
    elements at all, so the studio's `matrix` projection must be None."""
    from rmu.cli import app

    drafted = runner.invoke(app, ["onboard", "draft-template",
                                  "tests/fixtures/onboarding/target_form.pdf",
                                  "--no-ai"])
    assert drafted.exit_code == 0, drafted.output
    proposal_id = int(re.search(r"proposal: (\d+)", drafted.output).group(1))
    draft_path = Path(re.search(r"draft: (\S+)", drafted.output).group(1))
    return proposal_id, draft_path


def make_client(*, token: str = TOKEN, port: int = PORT,
                client_addr: tuple[str, int] = LOOPBACK, authenticate: bool = True):
    """TestClient against a fresh app with a known launch secret.

    `authenticate=True` performs the /?key= exchange so the session cookie is
    set; refusal tests pass False and forge their own headers."""
    from starlette.testclient import TestClient

    from rmu.studio.app import create_app
    from rmu.studio.auth import LaunchContext

    app = create_app(LaunchContext(token=token, port=port))
    client = TestClient(
        app, base_url=f"http://127.0.0.1:{port}", client=client_addr,
        follow_redirects=False,
    )
    if authenticate:
        exchanged = client.get(f"/?key={token}")
        assert exchanged.status_code in (302, 303), exchanged.text
        client.headers["X-Studio-Token"] = token
    return client


@pytest.fixture
def studio_client(studio_env):
    """Authenticated loopback client over a seeded store (most tests want this)."""
    return make_client()
