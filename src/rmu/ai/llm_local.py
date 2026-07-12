"""Tier-2 local LLM via Ollama's loopback HTTP API (A12b, research R2).

Deliberately uses the stdlib `urllib` against an explicit loopback URL rather
than the `ollama` client: one fewer dependency, and the loopback pin is
enforced in our own code (FR-002/analysis C1). A non-loopback host, an
unreachable server, a model that is not pulled, or a timeout all resolve to
"unavailable" (returning None), which the caller degrades on — value-map
proposals are simply skipped (per-tier degradation, FR-011). temperature 0 +
Ollama's JSON mode keep outputs deterministic and machine-parseable before the
strict gate (FR-008) ever runs.
"""

from __future__ import annotations

import ipaddress
import json
import urllib.error
import urllib.request
from urllib.parse import urlparse


def _is_loopback(host: str | None) -> bool:
    if host in ("localhost", "localhost.localdomain"):
        return True
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class LocalLLM:
    """Loopback-only Ollama client. Never raises to the caller — probes return
    bool, completions return the content string or None."""

    def __init__(self, host: str, model: str, timeout_seconds: int = 120):
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout_seconds
        self.loopback = _is_loopback(urlparse(self.host).hostname)
        self.reason: str | None = None if self.loopback else (
            f"ollama_host {self.host!r} is not loopback"
        )

    def _model_matches(self, names: set[str]) -> bool:
        repo = self.model.split(":")[0]
        return any(n == self.model or n.split(":")[0] == repo for n in names)

    def available(self) -> bool:
        """True iff a loopback Ollama is reachable AND the model is pulled."""
        if not self.loopback:
            return False
        try:
            with urllib.request.urlopen(f"{self.host}/api/tags", timeout=5) as resp:
                data = json.loads(resp.read())
        except (urllib.error.URLError, OSError, ValueError) as err:
            self.reason = f"ollama unreachable at {self.host} ({type(err).__name__})"
            return False
        names = {m.get("name", "") for m in data.get("models", [])}
        if not self._model_matches(names):
            self.reason = f"model {self.model!r} not pulled (have: {sorted(names)})"
            return False
        return True

    def complete_json(self, prompt: str, *, format_schema: dict | None = None) -> str | None:
        """Return the assistant's JSON content, or None on any failure.

        `format_schema` uses Ollama structured outputs — the model is constrained
        to emit JSON matching that schema (e.g. a top-level object with a
        `proposals` array), far more reliable than the bare `"json"` mode which
        only guarantees *some* valid JSON (models default to a lone object).
        `think` is disabled so reasoning models spend their budget on the answer.
        """
        if not self.loopback:
            return None
        payload = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": False,
            "format": format_schema if format_schema is not None else "json",
            "options": {"temperature": 0},
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/chat", data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
        except (urllib.error.URLError, OSError, ValueError) as err:
            self.reason = f"ollama call failed ({type(err).__name__})"
            return None
        return data.get("message", {}).get("content")
