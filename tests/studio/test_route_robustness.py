"""Studio route robustness / edge-case QA (feature 004).

Two classes of check:

* regression tests for malformed-but-plausible requests that used to reach an
  unhandled exception and return HTTP 500 instead of the studio's uniform
  refusal contract (422 DomainRefusal): non-integer template version, unequal
  value-map columns, and path-traversal value-map names. Each was found by QA,
  pinned, and the src/ fix now makes them pass.
* tests that VERIFY areas which behave correctly (terminal read-only, FR-006;
  approval-gate parity, FR-031) so a future regression is caught.

Everything drives the real HTTP surface through the shared fixtures; no server
process, no product code touched.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from rmu.cli import app
from rmu.studio.concurrency import content_hash
from tests.studio.conftest import LOOPBACK, PORT, TOKEN

runner = CliRunner()
EXEMPLAR = "seed/source_samples/Distribution-report.pdf"


def _nonraising_client():
    """Like `studio_client` but surfaces 500s as responses (so an assertion can
    describe the desired behaviour) rather than re-raising into the test."""
    from starlette.testclient import TestClient

    from rmu.studio.app import create_app
    from rmu.studio.auth import LaunchContext

    app_ = create_app(LaunchContext(token=TOKEN, port=PORT))
    client = TestClient(app_, base_url=f"http://127.0.0.1:{PORT}", client=LOOPBACK,
                        follow_redirects=False, raise_server_exceptions=False)
    exchanged = client.get(f"/?key={TOKEN}")
    assert exchanged.status_code in (302, 303)
    client.headers["X-Studio-Token"] = TOKEN
    return client


# --------------------------------------------------------------------------- #
# BUG A (confirmed, reachable): template approve with a non-integer version    #
# segment crashes with 500. proposals.py:161 does int(tver) after only         #
# checking that an '@' is present; 'name@v1', 'name@' and 'name@1.0' all raise #
# ValueError, uncaught. Expected: the same clean 422 the missing-'@' branch    #
# already returns.                                                             #
# --------------------------------------------------------------------------- #

def _resolve_all_elements(client, proposal_id: int) -> list:
    """Confirm every element so the approval gate is satisfied and control
    actually reaches the version parsing (the gate short-circuits otherwise)."""
    geo = client.get(f"/proposals/{proposal_id}/geometry").json()
    for page in sorted({e["page"] for e in geo["spatial"]}):
        client.post(f"/proposals/{proposal_id}/bulk-confirm", data={"page": page})
    geo = client.get(f"/proposals/{proposal_id}/geometry").json()
    for e in geo["non_spatial"]:
        if e["review_state"] not in ("confirmed", "corrected", "removed"):
            client.post(f"/proposals/{proposal_id}/elements/{e['id']}",
                        data={"action": "confirm"})
    return client.get(f"/proposals/{proposal_id}/geometry").json()["pending"]


@pytest.mark.parametrize("name", ["ias.defect_form@v1", "ias.defect_form@",
                                  "ias.defect_form@1.0", "@1"])
def test_template_approve_nonint_version_is_a_refusal(studio_env, template_proposal,
                                                      name):
    proposal_id, _ = template_proposal
    client = _nonraising_client()
    assert _resolve_all_elements(client, proposal_id) == []
    response = client.post(f"/proposals/{proposal_id}/approve",
                           data={"name": name, "by": "rayno"})
    assert response.status_code != 500, response.text
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# BUG B (confirmed, robustness): staging a value map with parallel arrays of   #
# unequal length crashes with 500. links.py:104 -> valuemaps.entries_from_    #
# parallel uses zip(..., strict=True); an omitted provenance column raises     #
# ValueError, uncaught. Not reachable from the honest form (each row emits all #
# three inputs) but any partial/hand-built POST 500s. Expected: a refusal.     #
# --------------------------------------------------------------------------- #

def test_stage_valuemap_unequal_arrays_is_a_refusal(studio_env, stub_session):
    session_id, _ = stub_session
    client = _nonraising_client()
    response = client.post(
        f"/sessions/{session_id}/links/priority/valuemap",
        data={"name": "sev", "source_value": ["1", "2"],
              "target_value": ["P4", "P1"], "provenance": []},
    )
    assert response.status_code != 500, response.text
    assert response.status_code == 422


@pytest.mark.parametrize("name", ["../escape", "a/b", "..", "sev/../../x"])
def test_stage_valuemap_unsafe_name_is_a_refusal(studio_env, stub_session, name):
    """A value-map name becomes a draft filename; a path-traversal name must be
    refused at the boundary, never write outside the drafts dir or 500."""
    session_id, _ = stub_session
    client = _nonraising_client()
    response = client.post(
        f"/sessions/{session_id}/links/priority/valuemap",
        data={"name": name, "source_value": ["1"], "target_value": ["P4"],
              "provenance": ["human"]},
    )
    assert response.status_code == 422, response.text


# --------------------------------------------------------------------------- #
# FR-006 verification (CLEAN): every mutating route on a terminal (approved)   #
# session is refused, and the approved view exposes no mutating affordance.    #
# --------------------------------------------------------------------------- #

def _approved_session(client) -> tuple[int, Path]:
    started = runner.invoke(app, [
        "map", "start", "--profile", "scopito.pdf.powerline@v2020",
        "--template", "interim.defect_csv@1", "--exemplar", EXEMPLAR, "--stub-ai"])
    assert started.exit_code == 0, started.output
    session_id = int(re.search(r"session: (\d+)", started.output).group(1))
    draft = Path(re.search(r"draft:\s+(\S+)", started.output).group(1))

    def h() -> str:
        return content_hash(draft.read_text(encoding="utf-8"))

    def doc() -> dict:
        return yaml.safe_load(draft.read_text(encoding="utf-8"))

    for field in [f for f, r in doc()["routes"].items() if r["tier"] == "T2"]:
        client.post(f"/sessions/{session_id}/routes/{field}",
                    data={"action": "accept", "base_hash": h()})
    if "comments" in doc()["routes"]:
        client.post(f"/sessions/{session_id}/routes/comments",
                    data={"action": "reject", "base_hash": h()})
    client.post(f"/sessions/{session_id}/routes",
                data={"field": "comments", "source": "finding.comments",
                      "base_hash": h()})
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
                    data={"name": name, "source_value": [e[0] for e in entries],
                          "target_value": [e[1] for e in entries],
                          "provenance": [e[2] for e in entries]})
        client.post(f"/sessions/{session_id}/links/{field}/valuemap/register",
                    data={"name": name, "base_hash": h()})
    client.post(f"/sessions/{session_id}/links/inspection_method/mechanism",
                data={"mechanism": "constant", "value": "UAV visual", "base_hash": h()})
    client.post(f"/sessions/{session_id}/links/inspection_date/mechanism",
                data={"mechanism": "formula", "base_hash": h(),
                      "spec": yaml.safe_dump({"fn": "date_format",
                          "args": [{"field": "header.report_date"},
                                   {"lit": "%Y-%m-%d"}]})})
    client.post(f"/sessions/{session_id}/links/contract_number/mechanism",
                data={"mechanism": "prompt", "key": "contract_number",
                      "label": "Client contract number", "required": "true",
                      "base_hash": h()})
    approved = client.post(f"/sessions/{session_id}/approve", data={"by": "rayno"})
    assert approved.status_code == 200, approved.text
    return session_id, draft


def test_terminal_session_refuses_every_mutation(studio_client):
    session_id, draft = _approved_session(studio_client)
    base_hash = content_hash(draft.read_text(encoding="utf-8"))
    mutations = {
        "accept route": studio_client.post(
            f"/sessions/{session_id}/routes/priority",
            data={"action": "accept", "base_hash": base_hash}),
        "reject route": studio_client.post(
            f"/sessions/{session_id}/routes/priority",
            data={"action": "reject", "base_hash": base_hash}),
        "create route": studio_client.post(
            f"/sessions/{session_id}/routes",
            data={"field": "newf", "source": "finding.comments",
                  "base_hash": base_hash}),
        "set constant": studio_client.post(
            f"/sessions/{session_id}/links/priority/mechanism",
            data={"mechanism": "constant", "value": "Z", "base_hash": base_hash}),
        "stage valuemap": studio_client.post(
            f"/sessions/{session_id}/links/priority/valuemap",
            data={"name": "x", "source_value": ["1"], "target_value": ["P4"],
                  "provenance": ["human"]}),
        "register valuemap": studio_client.post(
            f"/sessions/{session_id}/links/priority/valuemap/register",
            data={"name": "x", "base_hash": base_hash}),
        "approve again": studio_client.post(
            f"/sessions/{session_id}/approve", data={"by": "x"}),
        "abandon": studio_client.post(
            f"/sessions/{session_id}/abandon", data={}),
    }
    applied_or_crashed = {name: r.status_code for name, r in mutations.items()
                          if r.status_code == 200 or r.status_code >= 500}
    assert not applied_or_crashed, applied_or_crashed


def test_terminal_session_view_has_no_mutating_forms(studio_client):
    session_id, _ = _approved_session(studio_client)
    view = studio_client.get(f"/sessions/{session_id}")
    assert view.status_code == 200
    # every studio mutation is an hx-post; a read-only view must render none.
    assert "hx-post" not in view.text


# --------------------------------------------------------------------------- #
# FR-031 verification (CLEAN): studio approval refuses for exactly the CLI's   #
# reasons because it calls the very same approve_session. A draft session with #
# unresolved T3 stubs is refused with the CLI's gate reasons, not a crash.     #
# --------------------------------------------------------------------------- #

def test_studio_approve_gate_matches_cli_refusal(studio_client, manual_session):
    session_id, draft = manual_session
    # the CLI approve refuses this un-touched --no-ai draft (T3 stubs unrouted)
    cli = runner.invoke(app, ["map", "approve", str(session_id), "--by", "cli"])
    assert cli.exit_code != 0, cli.output

    web = studio_client.post(f"/sessions/{session_id}/approve", data={"by": "web"})
    assert web.status_code == 422, web.text
    # the studio surfaces the same class of reason verbatim (unrouted required
    # fields), never a 500 and never a silent approval.
    assert "unrouted" in web.text or "tier" in web.text
