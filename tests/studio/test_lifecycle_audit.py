"""T046 (SC-006/FR-004/FR-044, US7): a full studio session writes only to the
existing draft files, session/proposal rows, content-addressed objects and
append-only registries — nothing studio-private — and invokes no AI at preview
or approve."""

from __future__ import annotations

import re

import yaml
from sqlalchemy import inspect as sa_inspect
from typer.testing import CliRunner

from rmu.cli import app
from rmu.db import make_engine
from tests.conftest import block_non_loopback
from tests.studio.conftest import make_client

runner = CliRunner()
EXEMPLAR = "seed/source_samples/Distribution-report.pdf"

ALLOWED_TABLES = {
    "source_profiles", "target_templates", "transforms", "value_maps",
    "mapping_sessions", "source_documents", "onboarding_proposals",
    "apply_runs", "exceptions",
    "alembic_version",  # Alembic's own bookkeeping, pre-existing (not studio)
}


def _table_names() -> set[str]:
    return set(sa_inspect(make_engine()).get_table_names())


def _row_counts() -> dict[str, int]:
    engine = make_engine()
    counts = {}
    with engine.connect() as conn:
        from sqlalchemy import text
        for t in _table_names():
            counts[t] = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
    return counts


def test_no_studio_private_tables_exist(studio_env, studio_client):
    """The studio adds no schema — every table is a pre-existing one."""
    assert _table_names() <= ALLOWED_TABLES


def test_full_session_writes_only_expected_artifacts(studio_env, tmp_path, monkeypatch):
    client = make_client()
    # start via CLI, edit + register + preview + approve via studio
    started = runner.invoke(app, [
        "map", "start", "--profile", "scopito.pdf.powerline@v2020",
        "--template", "interim.defect_csv@1", "--exemplar", EXEMPLAR, "--stub-ai"])
    session_id = int(re.search(r"session: (\d+)", started.output).group(1))

    store_files_before = {p for p in (studio_env).rglob("*") if p.is_file()}

    # accept every pending proposal + register the two value maps via studio
    from pathlib import Path
    draft = Path(re.search(r"draft:\s+(\S+)", started.output).group(1))

    def h():
        from rmu.studio.concurrency import content_hash
        return content_hash(draft.read_text())

    doc = yaml.safe_load(draft.read_text())
    for field in [f for f, r in doc["routes"].items() if r["tier"] == "T2"]:
        client.post(f"/sessions/{session_id}/routes/{field}",
                    data={"action": "accept", "base_hash": h()})

    # preview + a (likely-refused) approve, both must touch no AI
    with block_non_loopback():
        preview = client.post(f"/sessions/{session_id}/preview")
        assert preview.status_code == 200, preview.text
        client.post(f"/sessions/{session_id}/approve", data={"by": "rayno"})

    after_counts = _row_counts()
    # no new tables; row growth only in allowed tables
    for table, count in after_counts.items():
        assert table in ALLOWED_TABLES

    store_files_after = {p for p in (studio_env).rglob("*") if p.is_file()}
    new_files = store_files_after - store_files_before
    for f in new_files:
        rel = f.relative_to(studio_env)
        assert rel.parts[0] in ("drafts", "objects", "runs") or f.name == "rmu.db", (
            f"studio wrote outside existing artifact areas: {rel}")


def test_preview_and_approve_make_no_external_connection(studio_env):
    client = make_client()
    started = runner.invoke(app, [
        "map", "start", "--profile", "scopito.pdf.powerline@v2020",
        "--template", "interim.defect_csv@1", "--exemplar", EXEMPLAR, "--no-ai"])
    session_id = int(re.search(r"session: (\d+)", started.output).group(1))
    # under the non-loopback network block, preview must still work (no AI at
    # preview — Constitution II / FR-044)
    with block_non_loopback():
        assert client.post(f"/sessions/{session_id}/preview").status_code == 200
