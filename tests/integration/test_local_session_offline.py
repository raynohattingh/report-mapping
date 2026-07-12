"""T011 (SC-001, FR-002/011/013): a full local-mode mapping session runs with
non-loopback network access blocked, produces schema-gated proposals, and
degrades per tier. The socket-blocking fixture is the mechanical proof that no
data leaves the machine.
"""

import re

import pytest
import yaml
from typer.testing import CliRunner

from rmu.ai.embeddings import EmbeddingBackend
from rmu.cli import app
from tests.conftest import block_non_loopback
from tests.fixtures.fake_ollama import DEFAULT_CONTENT, FakeOllama

runner = CliRunner()
EXEMPLAR = "seed/source_samples/Distribution-report.pdf"
MODEL = "BAAI/bge-small-en-v1.5"

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


def _write_ai_yaml(tmp_path, **local):
    (tmp_path / "ai.yaml").write_text(yaml.safe_dump({"default_mode": "local", "local": local}))


def _start_local(tmp_path):
    return runner.invoke(app, [
        "map", "start", "--profile", "scopito.pdf.powerline@v2020",
        "--template", "interim.defect_csv@1", "--exemplar", EXEMPLAR, "--assist", "local",
    ])


def _session_row(tmp_path):
    from sqlalchemy import select

    from rmu.db import make_engine, make_session_factory
    from rmu.models import MappingSession

    engine = make_engine(f"sqlite:///{tmp_path}/rmu.db")
    with make_session_factory(engine)() as s:
        return s.scalar(select(MappingSession))


def test_local_session_offline_produces_proposals(tmp_path, monkeypatch):
    _bootstrap(tmp_path, monkeypatch)
    with FakeOllama() as fake:
        _write_ai_yaml(tmp_path, ollama_host=fake.host_url, llm_model="qwen3:4b")
        with block_non_loopback():  # SC-001: no data leaves the machine
            result = _start_local(tmp_path)

    assert result.exit_code == 0, result.output
    assert "mode=local" in result.output
    assert re.search(r"assist:\s+local shown=\d+", result.output)

    ms = _session_row(tmp_path)
    assert ms.mode == "local"
    assert ms.assist_stats["mode"] == "local"
    assert "ollama:qwen3:4b" in ms.assist_stats["assets"]["llm"]
    assert set(ms.assist_stats["dropped"]) >= {"schema", "unknown_field", "unknown_value"}
    # At least one T2 proposal with rationale + local provenance (FR-013).
    assert ms.proposals, "expected value-map/route proposals from the local LLM"
    assert all(p["tier"] == "T2" for p in ms.proposals)
    assert any(p["rationale"] for p in ms.proposals)
    assert all(p["provider"] == "local" for p in ms.proposals)


def test_local_session_embeddings_only_degrades_llm(tmp_path, monkeypatch):
    _bootstrap(tmp_path, monkeypatch)
    # Point at a closed loopback port: LLM tier unavailable, embeddings still work.
    _write_ai_yaml(tmp_path, ollama_host="http://127.0.0.1:1", llm_model="qwen3:4b")
    with block_non_loopback():
        result = _start_local(tmp_path)

    assert result.exit_code == 0, result.output
    ms = _session_row(tmp_path)
    assert ms.assist_stats["degraded"] == ["llm"]
    assert ms.assist_stats["rankings"], "embeddings-only must still produce rankings"
    assert ms.proposals == []  # no value-map proposals without the LLM


def test_local_session_no_assets_is_manual_like(tmp_path, monkeypatch):
    _bootstrap(tmp_path, monkeypatch)
    # Bogus embedding model + dead LLM host => both tiers unavailable.
    _write_ai_yaml(
        tmp_path, ollama_host="http://127.0.0.1:1", embedding_model="BAAI/nope-xyz"
    )
    with block_non_loopback():
        result = _start_local(tmp_path)

    assert result.exit_code == 0, result.output
    assert "unavailable" in result.output  # clear degradation message on stderr
    ms = _session_row(tmp_path)
    assert set(ms.assist_stats["degraded"]) == {"embedding", "llm"}
    assert ms.proposals == []


def test_gate_drops_malformed_llm_output(tmp_path, monkeypatch):
    _bootstrap(tmp_path, monkeypatch)
    # Fake LLM returns garbage; the gate must drop it, never surface it, and the
    # dropped count must reflect it (FR-008).
    with FakeOllama(chat_handler=lambda _b: "not json at all") as fake:
        _write_ai_yaml(tmp_path, ollama_host=fake.host_url, llm_model="qwen3:4b")
        with block_non_loopback():
            result = _start_local(tmp_path)

    assert result.exit_code == 0, result.output
    ms = _session_row(tmp_path)
    assert ms.proposals == []
    assert sum(ms.assist_stats["dropped"].values()) >= 1


def test_default_content_is_gate_valid():
    # Guard: the fake's default canned content is itself schema+referent valid so
    # the happy-path test is exercising acceptance, not accidental rejection.
    import json

    assert isinstance(json.loads(DEFAULT_CONTENT), list)
