"""T027: AI-assisted session with the StubProvider (no network, A6).

US1 scenarios 1/2: proposals arrive tiered with rationale, visually distinct
on the review sheet, and can NEVER enter an approved transform without an
explicit human decision. The approved transform has the same form as a manual
one (SC-007).
"""

import re
from pathlib import Path

import yaml
from sqlalchemy import select
from typer.testing import CliRunner

from rmu.cli import app
from rmu.models import MappingSession, Transform

runner = CliRunner()
EXEMPLAR = "seed/source_samples/Distribution-report.pdf"


def _bootstrap(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    assert runner.invoke(app, ["seed", "load"]).exit_code == 0


def test_ai_session_proposals_require_decisions(tmp_path, monkeypatch):
    _bootstrap(tmp_path, monkeypatch)

    started = runner.invoke(app, [
        "map", "start", "--profile", "scopito.pdf.powerline@v2020",
        "--template", "interim.defect_csv@1", "--exemplar", EXEMPLAR, "--stub-ai",
    ])
    assert started.exit_code == 0, started.output
    session_id = int(re.search(r"session: (\d+)", started.output).group(1))
    draft_path = Path(re.search(r"draft:\s+(\S+)", started.output).group(1))

    # Scenario 1: complete draft — proposals carry tier T2 + one-line rationale;
    # unproposed required fields appear as T3.
    draft = yaml.safe_load(draft_path.read_text())
    tiers = {f: r["tier"] for f, r in draft["routes"].items()}
    assert tiers["finding_id"] == "T2"
    assert tiers["priority"] == "T2"
    assert tiers["contract_number"] == "T3"
    assert tiers["inspection_method"] == "T3"
    assert draft["routes"]["priority"]["rationale"]
    assert draft["routes"]["priority"]["value_map"]["name"] == "severity_to_priority"

    # Starter value-map files were emitted for human review, not auto-created.
    starters = re.findall(r"valuemap starter.*?: (\S+)", started.output)
    assert len(starters) == 2
    listed = runner.invoke(app, ["valuemap", "list"])
    assert listed.output.strip() == ""  # registry untouched without human action

    # Review sheet renders AI rows distinctly (T2 class) before any decision.
    review = runner.invoke(app, ["map", "review", "--session", str(session_id)])
    assert review.exit_code == 0
    html = Path(re.search(r"review sheet: (\S+)", review.output).group(1)).read_text()
    assert 'class="T2"' in html and 'class="T3"' in html
    assert "AI proposed" in html

    # Scenario 2: T2 proposals cannot enter an approved transform (exit 3).
    refused = runner.invoke(app, ["map", "approve", "--session", str(session_id),
                                  "--by", "rayno"])
    assert refused.exit_code == 3
    assert "T2" in refused.output

    # Human accepts: create the value maps from the starters, promote tiers.
    for starter in starters:
        name = re.search(r"valuemap\.(\w+)\.yaml", starter).group(1)
        assert runner.invoke(app, ["valuemap", "create", "--name", name,
                                   "--file", starter]).exit_code == 0
    doc = yaml.safe_load(draft_path.read_text())
    for field, route in list(doc["routes"].items()):
        if route["tier"] == "T2":
            route["tier"] = "T1" if route.get("value_map") else "T0"
    doc["routes"].pop("contract_number")
    doc["routes"].pop("inspection_method")
    doc["constants"]["inspection_method"] = "UAV visual"
    doc["prompts"] = [{"key": "contract_number", "label": "Client contract number",
                       "required": True}]
    # asset_name/inspection_date proposals accepted as-is; ensure required coverage
    draft_path.write_text(yaml.safe_dump(doc, sort_keys=True))

    approved = runner.invoke(app, ["map", "approve", "--session", str(session_id),
                                   "--by", "rayno"])
    assert approved.exit_code == 0, approved.output

    # Identical form to a manual transform + full lineage (FR-021, SC-007).
    from rmu.db import make_engine, make_session_factory

    engine = make_engine(f"sqlite:///{tmp_path}/rmu.db")
    with make_session_factory(engine)() as s:
        transform = s.scalar(select(Transform))
        parsed = yaml.safe_load(transform.yaml_body)
        assert set(parsed) <= {"meta", "routes", "constants", "formulas",
                               "prompts", "exceptions"}
        ms = s.scalar(select(MappingSession))
        assert ms.mode == "stub"
        assert len(ms.proposals) >= 6  # persisted with tier + rationale (FR-005)
        assert all(p["tier"] == "T2" and p["rationale"] for p in ms.proposals)
        actions = {d["action"] for d in ms.decisions}
        assert "accepted" in actions and "manual" in actions
