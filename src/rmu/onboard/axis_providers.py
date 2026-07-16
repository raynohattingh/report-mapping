"""Resolve the AxisInterpreter for the matrix interpret stage (feature 005).

Mirrors the 002 assist-mode precedence (`rmu.mapping.start._resolve_assist_mode`
/ `_check_external_consent`): `none`/`--no-ai` -> no interpreter; `local` ->
loopback Ollama vision model (default configured via `ai.yaml`'s `local.llm_model`,
A12b); `external` -> consent-gated, template-only for now. The local guarantee
(FR-002) is inherited from `rmu.ai.llm_local`'s loopback pinning — reused here,
not re-implemented. `resolve_axis_interpreter` never raises for `none`/`local`
(local unavailability degrades to `None`, per-tier degradation FR-011);
`external` always raises `ConsentRequired` for now — the actual Anthropic
vision call is a later feature, so both the unconsented and the consented path
refuse, with distinct messages.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from rmu.ai.config import AiConfig, has_consent
from rmu.ai.llm_local import _is_loopback
from rmu.onboard.interpret_matrix import AxisInterpreter

AXIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "row_axis": {
            "type": "object",
            "properties": {
                "number_column": {"type": ["integer", "null"]},
                "text_column": {"type": "integer"},
                "header_rows": {"type": "array", "items": {"type": "integer"}},
                "entries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "row": {"type": "integer"},
                            "number": {"type": ["string", "null"]},
                            "label": {"type": "string"},
                            "confidence": {"type": "number"},
                        },
                        "required": ["row", "label"],
                    },
                },
            },
        },
        "col_axis": {
            "type": "object",
            "properties": {
                "entries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "col": {"type": "integer"},
                            "label": {"type": "string"},
                            "confidence": {"type": "number"},
                        },
                        "required": ["col", "label"],
                    },
                },
            },
        },
        "notes": {"type": "string"},
    },
    "required": ["row_axis", "col_axis"],
}

_PROMPT = (
    "You are given a form table extracted from a PDF as a 2-D grid of cell text "
    "(row index i, column index j). It is a criteria x asset matrix: some left "
    "columns hold a criterion number and its text; some top rows are asset/tower "
    "headers; the rest are answer cells. Identify the row axis (criteria) and "
    "column axis (towers), labelling each BY ITS INDEX. Never invent an index "
    "that is not in the grid. Grid:\n{grid}\n"
)


class ConsentRequired(RuntimeError):
    """External assist requested without (or ahead of) recorded consent."""


class LocalVisionInterpreter:
    """Loopback-only Ollama vision client implementing `AxisInterpreter`.

    Never raises to the caller — `available()` returns bool, `interpret()`
    returns the parsed proposal dict or `None` on any failure (mirrors
    `rmu.ai.llm_local.LocalLLM`'s degrade-not-raise contract).
    """

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

    def interpret(
        self, grid: list[list[str]], page_image_png: bytes | None = None
    ) -> dict | None:
        """Propose axis labels for `grid`, constrained to `AXIS_SCHEMA`.

        `page_image_png=None` falls back to a text-grid-only prompt; otherwise
        the page image is attached (base64) to help disambiguate merged cells.
        Any transport/parse failure degrades to `None` — never raises.
        """
        if not self.loopback:
            return None
        message: dict[str, Any] = {
            "role": "user",
            "content": _PROMPT.format(grid=json.dumps(grid)),
        }
        if page_image_png is not None:
            message["images"] = [base64.b64encode(page_image_png).decode("ascii")]
        payload = json.dumps({
            "model": self.model,
            "messages": [message],
            "stream": False,
            "think": False,
            "format": AXIS_SCHEMA,
            "options": {"temperature": 0},
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/chat", data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
            content = data.get("message", {}).get("content")
            return json.loads(content) if content else None
        except (urllib.error.URLError, OSError, ValueError, KeyError) as err:
            self.reason = f"ollama call failed ({type(err).__name__})"
            return None


def resolve_axis_interpreter(
    mode: str, config: AiConfig, *, client: str | None
) -> AxisInterpreter | None:
    """Resolve the interpreter for an already-resolved assist `mode`.

    `mode` mirrors `rmu.mapping.start._resolve_assist_mode`'s output (the CLI's
    `--assist`/`RMU_ASSIST_MODE`/`ai.yaml` precedence is resolved upstream, same
    as feature 002). `none` -> `None`; `local` -> a `LocalVisionInterpreter`, or
    `None` if the loopback runtime/model is unavailable (degrade, never raise);
    `external` -> always `ConsentRequired` for now (the Anthropic vision call
    is a later feature) with a message distinguishing "no consent recorded"
    from "not yet enabled".
    """
    if mode == "none":
        return None
    if mode == "local":
        interpreter = LocalVisionInterpreter(
            config.ollama_host, config.llm_model, config.timeout_seconds
        )
        return interpreter if interpreter.available() else None
    if mode == "external":
        if not client or not has_consent(config, client):
            raise ConsentRequired(
                f"refused: no external-API consent recorded for client "
                f"{client!r}; record it with `rmu ai consent grant "
                f"--client {client} --by <owner>`"
            )
        raise ConsentRequired(
            "refused: external vision interpreter is not yet enabled "
            "(templates only, never client reports)"
        )
    raise ValueError(f"unknown assistance mode {mode!r}")
