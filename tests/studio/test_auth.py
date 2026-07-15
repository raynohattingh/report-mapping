"""FR-040/FR-040a, SC-003/SC-011: loopback bind is NOT trusted by itself.

Checks, in middleware order: loopback peer → Host allowlist → Origin /
Sec-Fetch-Site on mutations → per-launch token (URL-key exchange, cookie,
X-Studio-Token header on mutations). Every failure is a 403 carrying the
"restart via `rmu studio`" hint and never leaks which check failed beyond it.
"""

from __future__ import annotations

from tests.studio.conftest import PORT, TOKEN, make_client

HINT = "rmu studio"


def _assert_refused(response):
    assert response.status_code == 403, response.text
    assert HINT in response.text


def test_non_loopback_peer_refused():
    client = make_client(client_addr=("192.168.1.50", 4444), authenticate=False)
    _assert_refused(client.get(f"/?key={TOKEN}"))


def test_valid_key_exchanges_for_cookie_and_redirects():
    client = make_client(authenticate=False)
    response = client.get(f"/?key={TOKEN}")
    assert response.status_code in (302, 303)
    assert response.headers["location"].endswith("/dashboard")
    assert client.cookies.get("studio_session") == TOKEN
    set_cookie = response.headers["set-cookie"]
    assert "HttpOnly" in set_cookie and "SameSite=strict" in set_cookie.lower().replace(
        "samesite=strict", "SameSite=strict"
    )


def test_wrong_or_stale_key_refused():
    client = make_client(authenticate=False)
    _assert_refused(client.get("/?key=stale-token-from-a-previous-launch"))
    _assert_refused(client.get("/?key="))
    _assert_refused(client.get("/"))  # no key, no cookie


def test_request_without_cookie_refused():
    client = make_client(authenticate=False)
    _assert_refused(client.get("/dashboard"))


def test_forged_host_header_refused():
    client = make_client()  # authenticated
    _assert_refused(client.get("/dashboard", headers={"Host": "evil.example:80"}))
    # DNS-rebinding shape: attacker's name resolving to 127.0.0.1
    _assert_refused(client.get("/dashboard", headers={"Host": f"rebind.evil:{PORT}"}))


def test_cross_origin_mutation_refused():
    client = make_client()
    _assert_refused(client.post(
        "/sessions/1/abandon", headers={"Origin": "https://evil.example"},
    ))
    _assert_refused(client.post(
        "/sessions/1/abandon", headers={"Sec-Fetch-Site": "cross-site"},
    ))


def test_mutation_without_header_token_refused():
    client = make_client()
    del client.headers["X-Studio-Token"]  # cookie alone must not authorize a POST
    _assert_refused(client.post("/sessions/1/abandon"))


def test_mutation_with_wrong_header_token_refused():
    client = make_client()
    client.headers["X-Studio-Token"] = "not-the-launch-token"
    _assert_refused(client.post("/sessions/1/abandon"))


def test_same_origin_authenticated_get_passes_auth(studio_env):
    client = make_client()
    response = client.get("/dashboard")
    assert response.status_code == 200, response.text


def test_static_assets_require_cookie():
    client = make_client(authenticate=False)
    _assert_refused(client.get("/static/vendor/htmx.min.js"))
    authed = make_client()
    assert authed.get("/static/vendor/htmx.min.js").status_code == 200


def test_token_never_persisted_to_disk(studio_env):
    """The launch secret lives in process memory only (FR-040a edge case)."""
    client = make_client()
    client.get("/dashboard")
    on_disk = [
        p for p in studio_env.rglob("*")
        if p.is_file() and TOKEN.encode() in p.read_bytes()
    ]
    assert not on_disk, f"launch token found on disk: {on_disk}"
