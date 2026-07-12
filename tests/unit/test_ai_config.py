"""T007: ai.yaml loading, mode resolution, loopback validation, consent registry."""

import pytest
import yaml

from rmu.ai import config as aicfg


def test_defaults_when_no_file(tmp_path):
    cfg = aicfg.load_ai_config(tmp_path)
    assert cfg.default_mode == "local"
    assert cfg.ollama_host.startswith("http://127.0.0.1")
    assert cfg.embedding_model == "BAAI/bge-small-en-v1.5"
    assert cfg.llm_model == "qwen3:4b"
    assert cfg.timeout_seconds == 120
    assert cfg.consent == []


def test_mode_precedence(tmp_path):
    cfg = aicfg.load_ai_config(tmp_path)
    assert aicfg.resolve_mode("none", "local", cfg) == "none"        # flag wins
    assert aicfg.resolve_mode(None, "external", cfg) == "external"   # env next
    assert aicfg.resolve_mode(None, None, cfg) == "local"            # built-in default

    (tmp_path / "ai.yaml").write_text(yaml.safe_dump({"default_mode": "none"}))
    cfg2 = aicfg.load_ai_config(tmp_path)
    assert aicfg.resolve_mode(None, None, cfg2) == "none"            # file default


def test_invalid_mode_rejected(tmp_path):
    cfg = aicfg.load_ai_config(tmp_path)
    with pytest.raises(aicfg.AiConfigError):
        aicfg.resolve_mode("bogus", None, cfg)


def test_non_loopback_host_refused(tmp_path):
    (tmp_path / "ai.yaml").write_text(
        yaml.safe_dump({"local": {"ollama_host": "http://10.0.0.5:11434"}})
    )
    with pytest.raises(aicfg.AiConfigError):
        aicfg.load_ai_config(tmp_path)


def test_localhost_host_allowed(tmp_path):
    (tmp_path / "ai.yaml").write_text(
        yaml.safe_dump({"local": {"ollama_host": "http://localhost:11434"}})
    )
    cfg = aicfg.load_ai_config(tmp_path)
    assert cfg.ollama_host == "http://localhost:11434"


def test_schema_rejects_unknown_key(tmp_path):
    (tmp_path / "ai.yaml").write_text(yaml.safe_dump({"bogus_key": 1}))
    with pytest.raises(aicfg.AiConfigError):
        aicfg.load_ai_config(tmp_path)


def test_consent_grant_revoke_roundtrip(tmp_path):
    assert aicfg.has_consent(aicfg.load_ai_config(tmp_path), "demo") is False
    aicfg.grant_consent(tmp_path, "demo", "rayno", "demo data only")
    cfg = aicfg.load_ai_config(tmp_path)
    assert aicfg.has_consent(cfg, "demo") is True
    assert aicfg.has_consent(cfg, "other") is False  # consent is per-client
    aicfg.revoke_consent(tmp_path, "demo", "rayno")
    assert aicfg.has_consent(aicfg.load_ai_config(tmp_path), "demo") is False


def test_grant_preserves_other_settings(tmp_path):
    (tmp_path / "ai.yaml").write_text(
        yaml.safe_dump({"default_mode": "none", "local": {"llm_model": "gemma3:4b"}})
    )
    aicfg.grant_consent(tmp_path, "demo", "rayno", None)
    cfg = aicfg.load_ai_config(tmp_path)
    assert cfg.default_mode == "none"
    assert cfg.llm_model == "gemma3:4b"
    assert aicfg.has_consent(cfg, "demo")
