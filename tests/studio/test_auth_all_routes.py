"""T048 (SC-003/SC-011, US7): the auth ladder holds for EVERY registered route,
not just the ones exercised elsewhere, and no flag can rebind non-loopback."""

from __future__ import annotations

import pytest

from rmu.studio.auth import LaunchContext, request_allowed
from rmu.studio.launch import BIND_HOST
from tests.studio.conftest import PORT, TOKEN, make_client


def _walk(routes, out):
    for route in routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", "")
        if path and not path.startswith("/static") and path != "/":
            for method in methods:
                if method in ("GET", "POST"):
                    out.append((method, path))
        # this FastAPI version wraps included routers; the real APIRoutes live
        # on `original_router.routes`
        original = getattr(route, "original_router", None)
        if original is not None and getattr(original, "routes", None):
            _walk(original.routes, out)


def _registered_routes():
    from rmu.studio.app import create_app

    app = create_app(LaunchContext(token=TOKEN, port=PORT))
    out: list[tuple[str, str]] = []
    _walk(app.routes, out)
    return sorted(set(out))


ROUTES = _registered_routes()


def _concrete(path: str) -> str:
    """Fill path params with harmless concrete values."""
    return (path.replace("{session_id}", "1").replace("{proposal_id}", "1")
            .replace("{run_id}", "1").replace("{field}", "priority")
            .replace("{element_id}", "e1").replace("{sha}", "0" * 64))


@pytest.mark.parametrize("method,path", ROUTES)
def test_every_route_refuses_without_token(method, path):
    client = make_client(authenticate=False)  # no cookie, no header
    url = _concrete(path)
    response = client.request(method, url)
    assert response.status_code == 403, f"{method} {url} did not refuse: {response.status_code}"


@pytest.mark.parametrize("method,path", ROUTES)
def test_every_mutation_refuses_cross_origin(method, path):
    if method != "POST":
        return
    client = make_client()  # authenticated
    url = _concrete(path)
    response = client.request(method, url, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403, f"{method} {url} accepted cross-origin"


def test_scope_helper_rejects_non_loopback_peer():
    ctx = LaunchContext(token=TOKEN, port=PORT)
    scope = {"type": "http", "method": "GET", "path": "/dashboard",
             "headers": [(b"host", f"127.0.0.1:{PORT}".encode()),
                         (b"cookie", f"studio_session={TOKEN}".encode())],
             "client": ("10.0.0.9", 5000), "query_string": b""}
    assert not request_allowed(scope, ctx)
    scope["client"] = ("127.0.0.1", 5000)
    assert request_allowed(scope, ctx)


def test_bind_host_is_loopback_constant():
    assert BIND_HOST == "127.0.0.1"


def test_stale_token_from_previous_launch_refused():
    """A URL minted by a prior launch (different token) is refused."""
    client = make_client(token="current-launch-token", authenticate=False)
    assert client.get("/?key=previous-launch-token").status_code == 403
