"""T047 (FR-043/FR-040a, US7): the browser persists no document data — document
and preview responses are no-store, no client module uses localStorage/
sessionStorage, and the launch token never appears in a persisted response body."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.studio.conftest import TOKEN, make_client

JS_DIR = Path("src/rmu/studio/static/js")


@pytest.mark.parametrize("module", sorted(JS_DIR.glob("*.js")))
def test_no_browser_storage_in_js(module):
    text = module.read_text(encoding="utf-8")
    assert "localStorage" not in text, f"{module.name} uses localStorage (FR-043)"
    assert "sessionStorage" not in text, f"{module.name} uses sessionStorage (FR-043)"
    assert "indexedDB" not in text, f"{module.name} uses indexedDB (FR-043)"


def test_document_and_preview_responses_are_no_store(studio_env, manual_session):
    session_id, _ = manual_session
    client = make_client()
    geo = client.get(f"/sessions/{session_id}/geometry").json()
    sha = geo["source"]["pdf_sha"]
    pdf = client.get(f"/documents/{sha}/pdf")
    assert pdf.status_code == 200
    assert "no-store" in pdf.headers.get("cache-control", "")
    preview = client.post(f"/sessions/{session_id}/preview")
    file_resp = client.get(f"/sessions/{session_id}/preview/file")
    assert "no-store" in file_resp.headers.get("cache-control", "")
    assert preview.status_code == 200


def test_launch_token_never_in_rendered_pages(studio_env, manual_session):
    """The secret is delivered once via the URL→cookie exchange, and lives only
    in the cookie + the CSRF meta/header — never echoed into document bodies a
    browser might cache (the meta tag is intentional and non-persistent)."""
    session_id, _ = manual_session
    client = make_client()
    # data pages (JSON geometry, PDF bytes) must not carry the token
    assert TOKEN.encode() not in client.get(
        f"/sessions/{session_id}/geometry").content
    assert TOKEN.encode() not in client.get("/dashboard").content.replace(
        # the CSRF meta tag is the one allowed in-page reference; strip it
        f'<meta name="studio-token" content="{TOKEN}">'.encode(), b"")
