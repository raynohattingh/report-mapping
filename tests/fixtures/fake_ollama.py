"""Stdlib loopback Ollama stub (research R3).

Speaks the subset of the Ollama HTTP API that `rmu.ai.llm_local` uses —
`/api/tags` (availability) and `/api/chat` (completion) — bound to 127.0.0.1 on
an ephemeral port. Lets the offline session tests exercise the real tier-2 code
path without the actual runtime, and without leaving the machine (it IS the
machine). The chat handler is a callable so a test can return canned temp-0
JSON, malformed text (to exercise the drop path), or per-request content.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer

# Default: one well-formed value-map proposal, JSON-encoded as `format:json` would return.
DEFAULT_CONTENT = json.dumps([
    {
        "target_field": "priority",
        "from_path": "finding.severity",
        "rationale": "severity 1-5/? maps onto the priority vocabulary",
        "value_map_name": "severity_to_priority",
        "suggested_entries": [
            {"source_value": "5", "target_value": "P1"},
            {"source_value": "1", "target_value": "P4"},
        ],
    }
])

ChatHandler = Callable[[dict], str]


class FakeOllama:
    """Context manager yielding a running loopback Ollama stub.

    `chat_handler(request_body) -> content_str` produces the assistant message
    content for `/api/chat`. `models` backs `/api/tags`. `host_url` is the
    `http://127.0.0.1:<port>` base to point the client at.
    """

    def __init__(
        self,
        chat_handler: ChatHandler | None = None,
        models: tuple[str, ...] = ("qwen3:4b",),
    ):
        self._chat_handler = chat_handler or (lambda _body: DEFAULT_CONTENT)
        self._models = models
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def host_url(self) -> str:
        assert self._server is not None
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self) -> FakeOllama:
        handler_cls = self._make_handler()
        self._server = HTTPServer(("127.0.0.1", 0), handler_cls)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _make_handler(self):
        models = self._models
        chat_handler = self._chat_handler

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_a):  # silence test noise
                pass

            def _send(self, payload: dict, code: int = 200) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                if self.path.startswith("/api/tags"):
                    self._send({"models": [{"name": m} for m in models]})
                else:
                    self._send({"error": "not found"}, code=404)

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    body = json.loads(raw)
                except json.JSONDecodeError:
                    body = {}
                if self.path.startswith("/api/chat"):
                    content = chat_handler(body)
                    self._send({"message": {"role": "assistant", "content": content},
                                "done": True})
                else:
                    self._send({"error": "not found"}, code=404)

        return Handler
