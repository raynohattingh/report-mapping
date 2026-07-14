"""T028a — NEVER CUT (Constitution VIII, FR-015): PDF rendering is
byte-identical across re-runs (metadata pinned, research R9)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from rmu import store
from rmu.render.pdf_form import render_form_pdf
from rmu.render.pdf_overlay import render_overlay_pdf
from tests.golden.test_pdf_render_golden import FORM_CONFIG, OVERLAY_CONFIG, RECORD

FIX = Path("tests/fixtures/onboarding")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    from tests.fixtures.make_fixtures import _png

    return (
        tmp_path,
        store.put_file(FIX / "target_form.pdf"),
        store.put_file(FIX / "target_fixed.pdf"),
        store.put_bytes(_png((30, 120, 200))),
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_form_rerender_byte_identical(env):
    tmp_path, form_sha, _, _ = env
    config = {**FORM_CONFIG, "pdf_object": form_sha}
    hashes = []
    for i in range(2):
        out = tmp_path / f"run{i}.pdf"
        assert render_form_pdf(config, RECORD, out) == []
        hashes.append(_sha(out))
    assert hashes[0] == hashes[1]


def test_overlay_rerender_byte_identical(env):
    tmp_path, _, fixed_sha, photo_sha = env
    config = {**OVERLAY_CONFIG, "pdf_object": fixed_sha}
    record = {**RECORD, "photo_ref": photo_sha}
    hashes = []
    for i in range(2):
        out = tmp_path / f"run{i}.pdf"
        assert render_overlay_pdf(config, record, out) == []
        hashes.append(_sha(out))
    assert hashes[0] == hashes[1]
