"""Assistance configuration: modes, local model names, consent registry (R6, D8).

`ai.yaml` lives in the store directory (operational state, not a mapping
artifact — deliberately NOT one of the append-only registries). It is
schema-validated on load; a non-loopback `ollama_host` is refused outright so
the local guarantee (FR-002) cannot be config'd away. Consent entries are
per-client (FR-004) and only ever written by `grant_consent`/`revoke_consent`,
which the `rmu ai consent` commands wrap with an audit line.
"""

from __future__ import annotations

import datetime
import ipaddress
import json
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import jsonschema
import yaml

_SCHEMA_PATH = Path(__file__).parent / "schemas" / "ai_config.schema.json"
_schema = json.loads(_SCHEMA_PATH.read_text())

VALID_MODES = ("none", "local", "external")

_DEFAULTS = {
    "default_mode": "local",
    "embedding_model": "BAAI/bge-small-en-v1.5",  # A12a
    "llm_model": "qwen3:4b",  # A12b
    "vision_model": "qwen2.5vl:7b",  # feature 005: dedicated vision slot, distinct
    # from llm_model (docs/superpowers/specs/2026-07-15-matrix-target-onboarding-
    # design.md "Model substrate" — both must coexist so matrix interpret never
    # silently sends images to a text-only model).
    "ollama_host": "http://127.0.0.1:11434",
    "timeout_seconds": 120,
    "external_provider": "anthropic",
    "external_model": None,
}

CONFIG_FILENAME = "ai.yaml"


class AiConfigError(ValueError):
    """Raised on a malformed ai.yaml, unknown mode, or non-loopback host."""


@dataclass
class AiConfig:
    default_mode: str
    embedding_model: str
    llm_model: str
    vision_model: str
    ollama_host: str
    timeout_seconds: int
    external_provider: str
    external_model: str | None
    consent: list[dict] = field(default_factory=list)


def _is_loopback_host(host: str | None) -> bool:
    if host in (None, "", "localhost", "localhost.localdomain"):
        return host == "localhost" or host == "localhost.localdomain"
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _config_path(store_root: Path) -> Path:
    return Path(store_root) / CONFIG_FILENAME


def _read_raw(store_root: Path) -> dict:
    path = _config_path(store_root)
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise AiConfigError(f"{path}: top-level document must be a mapping")
    errors = sorted(
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in jsonschema.Draft202012Validator(_schema).iter_errors(raw)
    )
    if errors:
        raise AiConfigError(f"{path} is invalid: " + "; ".join(errors))
    return raw


def load_ai_config(store_root: Path) -> AiConfig:
    """Load + validate ai.yaml, filling defaults. Refuses a non-loopback host."""
    raw = _read_raw(store_root)
    local = raw.get("local", {})
    external = raw.get("external", {})

    ollama_host = local.get("ollama_host", _DEFAULTS["ollama_host"])
    if not _is_loopback_host(urlparse(ollama_host).hostname):
        raise AiConfigError(
            f"local.ollama_host must be loopback (127.0.0.0/8, ::1, localhost); "
            f"got {ollama_host!r} — the local guarantee cannot be configured away (FR-002)"
        )

    return AiConfig(
        default_mode=raw.get("default_mode", _DEFAULTS["default_mode"]),
        embedding_model=local.get("embedding_model", _DEFAULTS["embedding_model"]),
        llm_model=local.get("llm_model", _DEFAULTS["llm_model"]),
        vision_model=local.get("vision_model", _DEFAULTS["vision_model"]),
        ollama_host=ollama_host,
        timeout_seconds=int(local.get("timeout_seconds", _DEFAULTS["timeout_seconds"])),
        external_provider=external.get("provider", _DEFAULTS["external_provider"]),
        external_model=external.get("model", _DEFAULTS["external_model"]),
        consent=list(raw.get("consent", [])),
    )


def resolve_mode(flag: str | None, env: str | None, cfg: AiConfig) -> str:
    """Precedence: CLI flag > RMU_ASSIST_MODE env > ai.yaml default > 'local'."""
    mode = flag or env or cfg.default_mode or "local"
    if mode not in VALID_MODES:
        raise AiConfigError(
            f"unknown assistance mode {mode!r}; expected one of {', '.join(VALID_MODES)}"
        )
    return mode


def has_consent(cfg: AiConfig, client: str | None) -> bool:
    """True iff an explicit per-client consent entry exists (FR-004)."""
    if not client:
        return False
    return any(entry.get("client") == client for entry in cfg.consent)


def _write_raw(store_root: Path, raw: dict) -> None:
    # Validate before writing so we never persist an invalid file.
    errors = list(jsonschema.Draft202012Validator(_schema).iter_errors(raw))
    if errors:
        raise AiConfigError("refusing to write invalid ai.yaml: " + errors[0].message)
    _config_path(store_root).write_text(
        yaml.safe_dump(raw, sort_keys=True, allow_unicode=True), encoding="utf-8"
    )


def grant_consent(
    store_root: Path, client: str, granted_by: str, note: str | None = None
) -> dict:
    """Record per-client external-API consent (owner action). Idempotent-ish:
    re-granting refreshes granted_by/granted_at. Returns the stored entry."""
    if not client:
        raise AiConfigError("consent requires a non-empty client id")
    raw = _read_raw(store_root)
    consent = [e for e in raw.get("consent", []) if e.get("client") != client]
    entry = {
        "client": client,
        "granted_by": granted_by,
        "granted_at": datetime.date.today().isoformat(),
    }
    if note:
        entry["note"] = note
    consent.append(entry)
    raw["consent"] = consent
    _write_raw(store_root, raw)
    return entry


def revoke_consent(store_root: Path, client: str, revoked_by: str) -> bool:
    """Remove a client's consent entry. Returns True if one was removed."""
    raw = _read_raw(store_root)
    before = raw.get("consent", [])
    after = [e for e in before if e.get("client") != client]
    raw["consent"] = after
    _write_raw(store_root, raw)
    return len(after) < len(before)


def list_consent(cfg: AiConfig) -> list[dict]:
    return list(cfg.consent)
