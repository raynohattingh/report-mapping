"""Shared test helper: bootstrap the DB and approve a defect-CSV transform via
the real CLI flow (manual --no-ai session on the Distribution exemplar)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from rmu.cli import app

EXEMPLAR = "seed/source_samples/Distribution-report.pdf"

SEVERITY_ENTRIES = [
    {"source_value": s, "target_value": t, "provenance": "human"}
    for s, t in [("1", "P4"), ("2", "P4"), ("3", "P3"), ("4", "P2"),
                 ("5", "P1"), ("?", "POI")]
]
# NOTE: 'Lightning strike' is deliberately NOT mapped — batches containing it
# must produce oov_value exceptions, never guesses (US2 scenario 2).
ISSUE_ENTRIES = [
    {"source_value": s, "target_value": t, "provenance": "human"}
    for s, t in [("Conductor Damage", "C1"), ("Potential Hazard", "F1"),
                 ("Miscellaneous", "F12"), ("Corrosion", "A3")]
]


def approve_annexc_transform(runner, tmp_path: Path) -> int:
    """Manual session approving a transform for the docx report pack template.

    Assumes db init + seed + value maps already exist (run the defect-csv
    helper first)."""
    started = runner.invoke(app, [
        "map", "start", "--profile", "scopito.pdf.powerline@v2020",
        "--template", "interim.annexc_pack@1", "--exemplar", EXEMPLAR, "--no-ai",
    ])
    assert started.exit_code == 0, started.output
    session_id = int(re.search(r"session: (\d+)", started.output).group(1))
    draft_path = Path(re.search(r"draft:\s+(\S+)", started.output).group(1))

    doc = yaml.safe_load(draft_path.read_text())
    doc["routes"] = {
        "inspection_name": {"from": "header.inspection_name", "tier": "T0"},
        "company": {"from": "header.company", "tier": "T0"},
        "finding_id": {"from": "finding.id", "tier": "T0"},
        "source_severity": {"from": "finding.severity", "tier": "T0"},
        "priority": {"from": "finding.severity", "tier": "T1",
                     "value_map": {"name": "severity_to_priority", "version": 1}},
        "defect_code": {"from": "finding.issues", "tier": "T1",
                        "value_map": {"name": "issue_to_defect_code", "version": 1}},
        "comments": {"from": "finding.comments", "tier": "T0"},
    }
    doc["constants"] = {"inspection_method": "UAV visual"}
    doc["formulas"] = {"inspection_date": {
        "fn": "date_format",
        "args": [{"field": "header.report_date"}, {"lit": "%Y-%m-%d"}],
    }}
    doc["prompts"] = [{"key": "contract_number", "label": "Client contract number",
                       "required": True}]
    draft_path.write_text(yaml.safe_dump(doc, sort_keys=True))
    approved = runner.invoke(app, ["map", "approve", "--session", str(session_id),
                                   "--by", "rayno"])
    assert approved.exit_code == 0, approved.output
    return session_id


def approve_defect_csv_transform(
    runner, tmp_path: Path, issue_entries: list[dict] | None = None
) -> int:
    """db init + seed + manual session + valuemaps + approve. Returns session id."""
    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    assert runner.invoke(app, ["seed", "load"]).exit_code == 0

    started = runner.invoke(app, [
        "map", "start", "--profile", "scopito.pdf.powerline@v2020",
        "--template", "interim.defect_csv@1", "--exemplar", EXEMPLAR, "--no-ai",
    ])
    assert started.exit_code == 0, started.output
    session_id = int(re.search(r"session: (\d+)", started.output).group(1))
    draft_path = Path(re.search(r"draft:\s+(\S+)", started.output).group(1))

    for name, entries in [("severity_to_priority", SEVERITY_ENTRIES),
                          ("issue_to_defect_code", issue_entries or ISSUE_ENTRIES)]:
        f = tmp_path / f"vm_{name}.yaml"
        f.write_text(yaml.safe_dump({"entries": entries}))
        created = runner.invoke(app, ["valuemap", "create", "--name", name,
                                      "--file", str(f)])
        assert created.exit_code == 0, created.output

    doc = yaml.safe_load(draft_path.read_text())
    doc["routes"] = {
        "finding_id": {"from": "finding.id", "tier": "T0"},
        "asset_name": {"from": "header.inspection_name", "tier": "T0"},
        "source_severity": {"from": "finding.severity", "tier": "T0"},
        "priority": {"from": "finding.severity", "tier": "T1",
                     "value_map": {"name": "severity_to_priority", "version": 1}},
        "defect_code": {"from": "finding.issues", "tier": "T1",
                        "value_map": {"name": "issue_to_defect_code", "version": 1}},
        "comments": {"from": "finding.comments", "tier": "T0"},
        "user_tags": {"from": "finding.user_tags", "tier": "T0"},
        "source_page": {"from": "finding.page", "tier": "T0"},
    }
    doc["constants"] = {"inspection_method": "UAV visual"}
    doc["formulas"] = {"inspection_date": {
        "fn": "date_format",
        "args": [{"field": "header.report_date"}, {"lit": "%Y-%m-%d"}],
    }}
    doc["prompts"] = [{"key": "contract_number", "label": "Client contract number",
                       "required": True}]
    draft_path.write_text(yaml.safe_dump(doc, sort_keys=True))

    approved = runner.invoke(app, ["map", "approve", "--session", str(session_id),
                                   "--by", "rayno"])
    assert approved.exit_code == 0, approved.output
    return session_id
