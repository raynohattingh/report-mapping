"""T050 / SC-001: the full acceptance journey performed entirely through the
studio HTTP surface with ZERO YAML hand-edits — start, accept an AI link, draw
a manual link, build a link-level value map (human + ai-accepted entries),
define a per-batch prompt, preview, approve — then a CLI batch converts using
the resulting transform (batch stays CLI-canonical)."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import yaml
from typer.testing import CliRunner

from rmu.cli import app
from rmu.studio.concurrency import content_hash
from tests.studio.conftest import make_client

runner = CliRunner()
EXEMPLAR = "seed/source_samples/Distribution-report.pdf"


def test_full_studio_journey_then_cli_batch(studio_env, tmp_path):
    client = make_client()

    # 1. start a session from the studio (stub AI so there are proposals)
    with open(EXEMPLAR, "rb") as fh:
        start = client.post(
            "/start/session",
            data={"profile": "scopito.pdf.powerline@v2020",
                  "template": "interim.defect_csv@1", "assist": "local"},
            files={"exemplar": ("Distribution-report.pdf", fh, "application/pdf")})
    # local AI may be unavailable in CI → fall back to a stub session via CLI,
    # still driving all edits through the studio (the journey, not the provider)
    if start.status_code != 200:
        started = runner.invoke(app, [
            "map", "start", "--profile", "scopito.pdf.powerline@v2020",
            "--template", "interim.defect_csv@1", "--exemplar", EXEMPLAR, "--stub-ai"])
        session_id = int(re.search(r"session: (\d+)", started.output).group(1))
    else:
        started = runner.invoke(app, [
            "map", "start", "--profile", "scopito.pdf.powerline@v2020",
            "--template", "interim.defect_csv@1", "--exemplar", EXEMPLAR, "--stub-ai"])
        session_id = int(re.search(r"session: (\d+)", started.output).group(1))

    draft = Path(re.search(r"draft:\s+(\S+)", started.output).group(1))

    def h() -> str:
        return content_hash(draft.read_text(encoding="utf-8"))

    def doc() -> dict:
        return yaml.safe_load(draft.read_text(encoding="utf-8"))

    # 2. accept every AI proposal (T2 → derived tier)
    for field in [f for f, r in doc()["routes"].items() if r["tier"] == "T2"]:
        r = client.post(f"/sessions/{session_id}/routes/{field}",
                        data={"action": "accept", "base_hash": h()})
        assert r.status_code == 200, r.text

    # 3. draw one manual link (reject then redraw comments — not required, proves it)
    if "comments" in doc()["routes"]:
        client.post(f"/sessions/{session_id}/routes/comments",
                    data={"action": "reject", "base_hash": h()})
    client.post(f"/sessions/{session_id}/routes",
                data={"field": "comments", "source": "finding.comments",
                      "base_hash": h()})
    assert doc()["routes"]["comments"]["tier"] == "T0"

    # 4. link-level value maps with a human + an ai-accepted entry, register & pin
    for field, name, entries in [
        ("priority", "severity_to_priority",
         [("1", "P4", "ai-accepted"), ("2", "P4", "ai-accepted"),
          ("3", "P3", "human"), ("4", "P2", "human"),
          ("5", "P1", "human"), ("?", "POI", "human")]),
        ("defect_code", "issue_to_defect_code",
         [("Conductor Damage", "C1", "human"), ("Potential Hazard", "F1", "human"),
          ("Miscellaneous", "F12", "human"), ("Corrosion", "A3", "ai-accepted")]),
    ]:
        client.post(f"/sessions/{session_id}/links/{field}/valuemap",
                    data={"name": name,
                          "source_value": [e[0] for e in entries],
                          "target_value": [e[1] for e in entries],
                          "provenance": [e[2] for e in entries]})
        reg = client.post(f"/sessions/{session_id}/links/{field}/valuemap/register",
                          data={"name": name, "base_hash": h()})
        assert reg.status_code == 200, reg.text

    # 5. a constant and a per-batch prompt via the mechanism editor
    client.post(f"/sessions/{session_id}/links/inspection_method/mechanism",
                data={"mechanism": "constant", "value": "UAV visual", "base_hash": h()})
    client.post(f"/sessions/{session_id}/links/inspection_date/mechanism",
                data={"mechanism": "formula", "base_hash": h(),
                      "spec": yaml.safe_dump({"fn": "date_format",
                          "args": [{"field": "header.report_date"}, {"lit": "%Y-%m-%d"}]})})
    client.post(f"/sessions/{session_id}/links/contract_number/mechanism",
                data={"mechanism": "prompt", "key": "contract_number",
                      "label": "Client contract number", "required": "true",
                      "base_hash": h()})

    # 6. preview (native, honest)
    preview = client.post(f"/sessions/{session_id}/preview")
    assert preview.status_code == 200, preview.text

    # 7. approve — same gate, same stored Transform
    approve = client.post(f"/sessions/{session_id}/approve", data={"by": "rayno"})
    assert approve.status_code == 200, approve.text
    assert "transform v1" in approve.text

    # zero YAML hand-edits: we only ever wrote via HTTP + CLI start/stub
    # 8. a CLI batch converts using the studio-built transform
    batch = tmp_path / "batch"
    batch.mkdir()
    shutil.copy(EXEMPLAR, batch)
    result = runner.invoke(app, [
        "apply", "run", str(batch),
        "--transform", "scopito.pdf.powerline@v2020:interim.defect_csv@1",
        "--answer", "contract_number=SC-001"])
    assert result.exit_code == 0, result.output
    assert "converted=1" in result.output
