"""T012: parity foundation — no-op loads are byte-identical, drafts round-trip
through split/render unchanged, and a session part-edited on one surface is
finishable on the other in BOTH directions (FR-002, SC-005).

The cross-surface tests here exercise the exact functions the studio routes
delegate to; the HTTP-level equivalents land with the routes (T015/T024)."""

from __future__ import annotations

import yaml
from typer.testing import CliRunner

from rmu.cli import app
from rmu.mapping.session import render_draft, split_draft
from rmu.studio.concurrency import DraftLease

runner = CliRunner()

ROUTES = {
    "finding_id": {"from": "finding.id", "tier": "T0"},
    "asset_name": {"from": "header.inspection_name", "tier": "T0"},
    "source_severity": {"from": "finding.severity", "tier": "T0"},
    "priority": {"from": "finding.severity", "tier": "T0"},
    "defect_code": {"from": "finding.issues", "tier": "T0"},
    "comments": {"from": "finding.comments", "tier": "T0"},
    "user_tags": {"from": "finding.user_tags", "tier": "T0"},
    "source_page": {"from": "finding.page", "tier": "T0"},
}


def complete_doc(doc: dict) -> None:
    """Route every required field of interim.defect_csv@1 (helpers.py shape)."""
    doc["routes"] = dict(ROUTES)
    doc["constants"] = {"inspection_method": "UAV visual"}
    doc["formulas"] = {"inspection_date": {
        "fn": "date_format",
        "args": [{"field": "header.report_date"}, {"lit": "%Y-%m-%d"}],
    }}
    doc["prompts"] = [{"key": "contract_number", "label": "Client contract number",
                       "required": True}]


def test_noop_load_leaves_draft_byte_identical(manual_session):
    _, draft_path = manual_session
    before = draft_path.read_bytes()
    DraftLease().load(draft_path)  # what every studio GET does
    assert draft_path.read_bytes() == before


def test_split_render_roundtrip_is_byte_identical(manual_session):
    _, draft_path = manual_session
    text = draft_path.read_text(encoding="utf-8")
    banner, doc = split_draft(text)
    assert banner.startswith("# RMU draft transform")
    assert render_draft(banner, doc) == text


def test_cli_started_studio_edited_cli_finished(manual_session):
    """CLI start → studio-path edit (lease + split/render) → CLI approve."""
    session_id, draft_path = manual_session
    lease = DraftLease()
    text, base_hash = lease.load(draft_path)

    def studio_edit(current: str) -> str:
        banner, doc = split_draft(current)
        complete_doc(doc)
        return render_draft(banner, doc)

    lease.apply_edit(draft_path, base_hash, studio_edit)

    approved = runner.invoke(app, ["map", "approve", "--session", str(session_id),
                                   "--by", "rayno"])
    assert approved.exit_code == 0, approved.output
    assert "approved: transform v1" in approved.output


def test_cli_started_hand_edited_studio_finished(studio_env, runner, manual_session):
    """CLI start → analyst hand-edit of the YAML → studio-path approve."""
    from rmu.db import make_engine, make_session_factory
    from rmu.mapping.approve import approve_session

    session_id, draft_path = manual_session
    doc = yaml.safe_load(draft_path.read_text())  # hand-edit: comments lost, fine
    complete_doc(doc)
    draft_path.write_text(yaml.safe_dump(doc, sort_keys=True))

    with make_session_factory(make_engine())() as s:
        transform, ms = approve_session(s, session_id, "rayno")  # studio's call
        assert transform.version == 1
        assert ms.status == "approved"
        assert transform.yaml_body == draft_path.read_text(encoding="utf-8")
