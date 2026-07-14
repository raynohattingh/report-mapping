"""T017 (FR-016): proposals are generated once and persisted; re-opening never
silently changes them, and explicit regeneration replaces the set while keeping
the prior generation in superseded history. Refused on approved sessions."""

import re

from typer.testing import CliRunner

from rmu.cli import app
from tests.integration.helpers import approve_defect_csv_transform

runner = CliRunner()
EXEMPLAR = "seed/source_samples/Distribution-report.pdf"


def _bootstrap(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    monkeypatch.delenv("RMU_ASSIST_MODE", raising=False)
    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    assert runner.invoke(app, ["seed", "load"]).exit_code == 0


def _session(tmp_path):
    from sqlalchemy import select

    from rmu.db import make_engine, make_session_factory
    from rmu.models import MappingSession

    engine = make_engine(f"sqlite:///{tmp_path}/rmu.db")
    with make_session_factory(engine)() as s:
        return s.scalar(select(MappingSession))


def test_regenerate_supersedes_prior_stub_session(tmp_path, monkeypatch):
    _bootstrap(tmp_path, monkeypatch)
    started = runner.invoke(app, [
        "map", "start", "--profile", "scopito.pdf.powerline@v2020",
        "--template", "interim.defect_csv@1", "--exemplar", EXEMPLAR, "--stub-ai",
    ])
    assert started.exit_code == 0, started.output
    session_id = int(re.search(r"session: (\d+)", started.output).group(1))
    before = _session(tmp_path)
    n_before = len(before.proposals)
    assert n_before >= 6

    regen = runner.invoke(app, ["map", "regenerate", "--session", str(session_id)])
    assert regen.exit_code == 0, regen.output
    assert "superseded" in regen.output

    after = _session(tmp_path)
    # A superseded generation was recorded, holding the prior proposal set.
    assert len(after.assist_stats["superseded"]) == 1
    assert len(after.assist_stats["superseded"][0]["proposals"]) == n_before
    # Stub is deterministic: the regenerated set matches (persistence, not drift).
    assert len(after.proposals) == n_before


def test_regenerate_refused_on_approved_session(tmp_path, monkeypatch):
    _bootstrap(tmp_path, monkeypatch)  # NEVER run against the real dev DB
    session_id = approve_defect_csv_transform(runner, tmp_path)
    refused = runner.invoke(app, ["map", "regenerate", "--session", str(session_id)])
    assert refused.exit_code == 3
    assert "approved" in refused.output


def test_reopening_does_not_change_persisted_proposals(tmp_path, monkeypatch):
    _bootstrap(tmp_path, monkeypatch)
    started = runner.invoke(app, [
        "map", "start", "--profile", "scopito.pdf.powerline@v2020",
        "--template", "interim.defect_csv@1", "--exemplar", EXEMPLAR, "--stub-ai",
    ])
    session_id = int(re.search(r"session: (\d+)", started.output).group(1))
    proposals_1 = _session(tmp_path).proposals
    # Re-render the review sheet (a re-open) — proposals must be untouched.
    assert runner.invoke(app, ["map", "review", "--session", str(session_id)]).exit_code == 0
    assert _session(tmp_path).proposals == proposals_1
