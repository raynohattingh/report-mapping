"""T026 — verify-on-approve for templates (FR-009/FR-022/FR-025): a sample
test render must round-trip before anything registers; fail-closed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rmu import store
from rmu.cli import app
from rmu.db import make_engine, make_session_factory
from rmu.onboard.analyze_target import analyze
from rmu.onboard.approve import VerifyFailure, approve_template
from rmu.onboard.proposal import Proposal

runner = CliRunner()
FIX = Path("tests/fixtures/onboarding")


@pytest.fixture()
def session(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    factory = make_session_factory(make_engine())
    with factory() as s:
        yield s


def _confirmed(session, fixture: str, kind: str) -> Proposal:
    store.put_file(FIX / fixture)
    document = analyze(FIX / fixture, kind=kind)
    for e in document["elements"]:
        e["review_state"] = "confirmed"
    return Proposal.create(session, document)


def test_form_template_registers_with_pdf_declared_required(session):
    p = _confirmed(session, "target_form.pdf", "form")
    row = approve_template(session, p, "ias.defect_form", 1, "rayno")

    assert row.interim is False and row.institution == "ONBOARDED"
    config = json.loads(store.get_bytes(row.template_files["template.json"]))
    assert config["kind"] == "pdf_form" and config["cardinality"] == "per_record"
    # PDF-declared required flags became the required schema (FR-025)
    assert "asset_id" in row.required_schema["required"]
    assert "comments" not in row.required_schema["required"]
    assert p.status == "approved" and p.row.resulting_template_id == row.id


def test_overlay_template_registers_all_regions_required(session):
    p = _confirmed(session, "target_fixed.pdf", "fixed_layout")
    row = approve_template(session, p, "ias.record_sheet", 1, "rayno")

    config = json.loads(store.get_bytes(row.template_files["template.json"]))
    assert config["kind"] == "pdf_overlay"
    kinds = {r["kind"] for r in config["regions"]}
    assert kinds == {"text", "image"}
    assert set(row.required_schema["required"]) == {
        r["target_field"] for r in config["regions"]
    }


def test_grid_template_onboards_end_to_end(session):
    """A line-grid target (no AcroForm, no area rects) must register as a
    pdf_overlay template whose verify render/roundtrip passes."""
    p = _confirmed(session, "target_grid.pdf", "fixed_layout")
    row = approve_template(session, p, "synthetic_grid", 1, "rayno")

    assert p.status == "approved" and p.row.verify_report["ok"] is True
    assert row.name == "synthetic_grid" and row.interim is False
    config = json.loads(store.get_bytes(row.template_files["template.json"]))
    assert config["kind"] == "pdf_overlay"
    assert len(config["regions"]) == 11  # every blank grid cell registered


def test_broken_region_fails_the_test_render_and_stays_draft(session):
    p = _confirmed(session, "target_fixed.pdf", "fixed_layout")
    # analyst 'corrects' a region to an unusably narrow box: sample cannot fit
    doc = p.document
    region = next(e for e in doc["elements"] if e["element_kind"] == "overlay_region"
                  and e["payload"]["kind"] == "text")
    region["review_state"] = "corrected"
    bad_bbox = [region["payload"]["bbox"][0], region["payload"]["bbox"][1],
                region["payload"]["bbox"][0] + 2, region["payload"]["bbox"][3]]
    region["corrected_payload"] = {**region["payload"], "bbox": bad_bbox}

    with pytest.raises(VerifyFailure):
        approve_template(session, p, "ias.broken", 1, "rayno")
    assert p.status == "draft"
    assert p.row.verify_report["ok"] is False
