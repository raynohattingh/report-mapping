"""Resolver/schema/consent tests for feature 005's axis interpreter (Task 5).

Zero network: only the resolver's mode precedence, the AXIS_SCHEMA shape, and
the external-mode consent refusal are exercised — never a live (or fake)
Ollama transport.
"""
from __future__ import annotations

import pytest

from rmu.ai.config import AiConfig
from rmu.onboard.axis_providers import AXIS_SCHEMA, ConsentRequired, resolve_axis_interpreter


def _cfg(consent=None, vision_model="qwen2.5vl:7b"):
    return AiConfig(
        default_mode="local",
        embedding_model="x",
        llm_model="qwen3:4b",
        vision_model=vision_model,
        ollama_host="http://127.0.0.1:11434",
        timeout_seconds=60,
        external_provider="anthropic",
        external_model=None,
        consent=consent or [],
    )


def test_none_mode_returns_no_interpreter():
    assert resolve_axis_interpreter("none", _cfg(), client=None) is None


def test_local_mode_degrades_to_none_when_unavailable():
    # No Ollama is running on this port during tests, so this must degrade,
    # never raise (FR-011 per-tier degradation).
    cfg = _cfg()
    assert resolve_axis_interpreter("local", cfg, client=None) is None


def test_external_without_consent_refuses():
    with pytest.raises(ConsentRequired):
        resolve_axis_interpreter("external", _cfg(), client="acme")


def test_external_without_client_refuses():
    with pytest.raises(ConsentRequired):
        resolve_axis_interpreter("external", _cfg(), client=None)


def test_external_with_consent_still_refuses_not_yet_enabled():
    cfg = _cfg(consent=[{"client": "acme", "granted_by": "owner"}])
    with pytest.raises(ConsentRequired, match="not yet enabled"):
        resolve_axis_interpreter("external", cfg, client="acme")


def test_unknown_mode_raises_value_error():
    with pytest.raises(ValueError):
        resolve_axis_interpreter("bogus", _cfg(), client=None)


def test_local_mode_resolves_dedicated_vision_model(monkeypatch):
    # 005 review finding: the interpret vision layer must bind to its own
    # `vision_model` slot, never the 002 text `llm_model` (default qwen3:4b),
    # or local vision interpret would silently send images to a text model.
    from rmu.onboard import axis_providers as ap

    monkeypatch.setattr(ap.LocalVisionInterpreter, "available", lambda self: True)
    cfg = _cfg(vision_model="qwen2.5vl:7b")
    interpreter = resolve_axis_interpreter("local", cfg, client=None)
    assert interpreter is not None
    assert interpreter.model == "qwen2.5vl:7b"
    assert interpreter.model != cfg.llm_model


def test_axis_schema_shape():
    assert AXIS_SCHEMA["type"] == "object"
    assert "row_axis" in AXIS_SCHEMA["properties"]
    assert "col_axis" in AXIS_SCHEMA["properties"]
    assert "entries" in AXIS_SCHEMA["properties"]["row_axis"]["properties"]
    assert "entries" in AXIS_SCHEMA["properties"]["col_axis"]["properties"]
