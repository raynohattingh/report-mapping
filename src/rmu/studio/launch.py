"""`rmu studio` launcher (contracts/cli-studio.md, FR-040/FR-040a, D11).

The bind address is HARDCODED to 127.0.0.1 — no flag or config can widen it
(same loopback rule the local AI layer enforces for its LLM host). The
per-launch secret is generated here, printed once inside the URL, and held in
process memory only; it dies with the process, so stale URLs are refused by
the next launch's fresh token.
"""

from __future__ import annotations

import secrets
import socket
import webbrowser

BIND_HOST = "127.0.0.1"  # non-configurable (FR-040, SC-003)
PORT_RANGE = range(8765, 8786)


class NoFreePortError(RuntimeError):
    pass


def pick_port(preferred: int | None = None) -> int:
    candidates = [preferred] if preferred else list(PORT_RANGE)
    for port in candidates:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((BIND_HOST, port))
            except OSError:
                continue
            return port
    raise NoFreePortError(
        f"no free port in {candidates[0]}-{candidates[-1]}; pass --port"
    )


def run_studio(port: int | None = None, open_browser: bool = True) -> None:
    import uvicorn

    from rmu.studio.app import create_app
    from rmu.studio.auth import LaunchContext

    bound_port = pick_port(port)
    ctx = LaunchContext(token=secrets.token_urlsafe(32), port=bound_port)
    url = f"http://{BIND_HOST}:{bound_port}/?key={ctx.token}"
    # Flush immediately: the URL carries the launch secret and the user needs it
    # before uvicorn takes over the loop (stdout is block-buffered when piped).
    print(f"studio: {url}", flush=True)
    print("studio: localhost only; Ctrl-C to stop. Stale URLs from previous "
          "launches are refused.", flush=True)
    if open_browser:
        webbrowser.open(url)
    uvicorn.run(create_app(ctx), host=BIND_HOST, port=bound_port,
                log_level="warning")
