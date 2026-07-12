"""T026 (US3, FR-006/007/008): local value-map proposals arrive with rationales,
land in the review flow unaccepted (registry untouched), and malformed model
output is dropped with the aggregate count surfaced on the review sheet.
"""

import json
import re
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from rmu.ai.embeddings import EmbeddingBackend
from rmu.cli import app
from tests.conftest import block_non_loopback
from tests.fixtures.fake_ollama import FakeOllama

runner = CliRunner()
EXEMPLAR = "seed/source_samples/Distribution-report.pdf"
MODEL = "BAAI/bge-small-en-v1.5"
_PRIORITY = {"5": "P1", "4": "P2", "3": "P3", "2": "P4", "1": "P4", "?": "POI"}

pytestmark = pytest.mark.skipif(
    not EmbeddingBackend(MODEL).available(),
    reason="bge-small cache not warmed (run `rmu ai setup`)",
)


def _bootstrap(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path))
    monkeypatch.setenv("RMU_DB_URL", f"sqlite:///{tmp_path}/rmu.db")
    monkeypatch.delenv("RMU_ASSIST_MODE", raising=False)
    assert runner.invoke(app, ["db", "init"]).exit_code == 0
    assert runner.invoke(app, ["seed", "load"]).exit_code == 0


def _observed_severities():
    from rmu.extract import scopito_pdf_powerline as ext
    from rmu.seed import profile_config

    normalized = ext.extract(Path(EXEMPLAR), profile_config("scopito.pdf.powerline@v2020"))
    return sorted({f["severity"] for f in normalized["findings"]})


def _valuemap_content(severities):
    return json.dumps([{
        "target_field": "priority",
        "from_path": "finding.severity",
        "rationale": "severity 1-5/? maps onto the priority vocabulary",
        "value_map_name": "severity_to_priority",
        "suggested_entries": [
            {"source_value": s, "target_value": _PRIORITY.get(s, "POI")} for s in severities
        ],
    }])


def _write_ai_yaml(tmp_path, host):
    (tmp_path / "ai.yaml").write_text(
        yaml.safe_dump({"default_mode": "local", "local": {"ollama_host": host}})
    )


def _start_local(tmp_path):
    return runner.invoke(app, [
        "map", "start", "--profile", "scopito.pdf.powerline@v2020",
        "--template", "interim.defect_csv@1", "--exemplar", EXEMPLAR, "--assist", "local",
    ])


def _session(tmp_path):
    from sqlalchemy import select

    from rmu.db import make_engine, make_session_factory
    from rmu.models import MappingSession

    engine = make_engine(f"sqlite:///{tmp_path}/rmu.db")
    with make_session_factory(engine)() as s:
        return s.scalar(select(MappingSession))


def test_valuemap_proposals_have_rationales_and_stay_unaccepted(tmp_path, monkeypatch):
    _bootstrap(tmp_path, monkeypatch)
    content = _valuemap_content(_observed_severities())
    with FakeOllama(chat_handler=lambda _b: content) as fake:
        _write_ai_yaml(tmp_path, fake.host_url)
        with block_non_loopback():
            started = _start_local(tmp_path)
    assert started.exit_code == 0, started.output

    ms = _session(tmp_path)
    vm = [p for p in ms.proposals if p.get("value_map_name") == "severity_to_priority"]
    assert vm, "expected a severity->priority value-map proposal"
    assert vm[0]["rationale"]                         # one-line rationale (FR-006)
    assert vm[0]["tier"] == "T2"                       # nothing auto-accepted (FR-007)
    assert vm[0]["suggested_entries"]                  # entries survived the gate

    # A starter file was emitted for human review; the registry stays empty until
    # the human explicitly runs `valuemap create` (Constitution V).
    assert "valuemap starter" in started.output
    assert runner.invoke(app, ["valuemap", "list"]).output.strip() == ""


def test_malformed_output_dropped_and_counted_on_review_sheet(tmp_path, monkeypatch):
    _bootstrap(tmp_path, monkeypatch)
    with FakeOllama(chat_handler=lambda _b: "definitely not json") as fake:
        _write_ai_yaml(tmp_path, fake.host_url)
        with block_non_loopback():
            started = _start_local(tmp_path)
    assert started.exit_code == 0, started.output
    session_id = int(re.search(r"session: (\d+)", started.output).group(1))

    ms = _session(tmp_path)
    assert ms.proposals == []
    assert sum(ms.assist_stats["dropped"].values()) >= 1

    review = runner.invoke(app, ["map", "review", "--session", str(session_id)])
    assert review.exit_code == 0, review.output
    html = Path(re.search(r"review sheet: (\S+)", review.output).group(1)).read_text()
    assert "dropped 1" in html  # aggregate count always visible (FR-008)
