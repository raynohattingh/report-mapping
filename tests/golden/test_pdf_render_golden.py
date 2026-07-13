"""T028a — golden + round-trip tests for PDF rendering (SC-004/SC-005).

Form: every value read back equals the applied value exactly.
Overlay: frozen (text, x0, top) tuples — the registered-coordinates proof.
Golden data self-captures on first run (make_golden pattern); committed
thereafter, drift fails the build.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rmu import store
from rmu.render.pdf_form import render_form_pdf
from rmu.render.pdf_overlay import render_overlay_pdf
from rmu.render.pdf_roundtrip import verify

FIX = Path("tests/fixtures/onboarding")
GOLDEN = Path("tests/golden/data/overlay_regions.json")

FORM_CONFIG = {
    "kind": "pdf_form",
    "cardinality": "per_record",
    "fields": [
        {"field_id": "asset_id", "target_field": "asset_name", "kind": "text"},
        {"field_id": "defect_code", "target_field": "defect_code", "kind": "text",
         "max_len": 6},
        {"field_id": "priority", "target_field": "priority", "kind": "choice",
         "options": ["P1", "P2", "P3", "P4"]},
        {"field_id": "comments", "target_field": "comments", "kind": "text"},
        {"field_id": "reinspect", "target_field": "reinspect", "kind": "checkbox"},
    ],
}

OVERLAY_CONFIG = {
    "kind": "pdf_overlay",
    "cardinality": "per_record",
    "regions": [
        {"label": "Asset ID:", "target_field": "asset_name", "kind": "text",
         "page": 1, "bbox": [150, 746, 370, 762]},
        {"label": "Defect code:", "target_field": "defect_code", "kind": "text",
         "page": 1, "bbox": [150, 706, 370, 722]},
        {"label": "Priority:", "target_field": "priority", "kind": "text",
         "page": 1, "bbox": [150, 666, 370, 682]},
        {"label": "Photo:", "target_field": "photo_ref", "kind": "image",
         "page": 1, "bbox": [400, 600, 550, 740]},
    ],
}

RECORD = {"asset_name": "TWR-0114", "defect_code": "C1", "priority": "P2",
          "comments": "hairline crack on cross-arm", "reinspect": "yes"}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    form_sha = store.put_file(FIX / "target_form.pdf")
    fixed_sha = store.put_file(FIX / "target_fixed.pdf")
    photo_sha = store.put_bytes((FIX / "survey_report_a.pdf").read_bytes()[:0] or b"")
    # a real image for the photo region: reuse a deterministic PNG
    from tests.fixtures.make_fixtures import _png

    photo_sha = store.put_bytes(_png((30, 120, 200)))
    return tmp_path, form_sha, fixed_sha, photo_sha


def test_form_fill_round_trips_exactly(env):
    tmp_path, form_sha, _, _ = env
    config = {**FORM_CONFIG, "pdf_object": form_sha}
    out = tmp_path / "form_0001.pdf"

    assert render_form_pdf(config, RECORD, out) == []
    report = verify(config, out, RECORD)
    assert report.ok, report.mismatches  # SC-004: exact round-trip, every field


def test_form_never_truncates_or_guesses(env):
    tmp_path, form_sha, _, _ = env
    config = {**FORM_CONFIG, "pdf_object": form_sha}

    too_long = {**RECORD, "defect_code": "TOOLONG9"}
    problems = render_form_pdf(config, too_long, tmp_path / "x.pdf")
    assert [p.kind for p in problems] == ["oversize_value"]
    assert not (tmp_path / "x.pdf").exists()  # no half-written output

    missing = {k: v for k, v in RECORD.items() if k != "asset_name"}
    problems = render_form_pdf(config, missing, tmp_path / "y.pdf")
    assert [p.kind for p in problems] == ["missing_required"]


def test_overlay_renders_at_registered_coordinates(env):
    tmp_path, _, fixed_sha, photo_sha = env
    config = {**OVERLAY_CONFIG, "pdf_object": fixed_sha}
    record = {**RECORD, "photo_ref": photo_sha}
    out = tmp_path / "overlay_0001.pdf"

    assert render_overlay_pdf(config, record, out) == []
    report = verify(config, out, record)
    assert report.ok, report.mismatches  # text in-region + image pixel match

    # SC-005 golden: frozen (value, x0, top) for every text region
    import pdfplumber

    with pdfplumber.open(out) as pdf:
        page = pdf.pages[0]
        placed = sorted(
            (w["text"], round(w["x0"]), round(w["top"]))
            for w in page.extract_words()
            if w["text"] in {"TWR-0114", "C1", "P2"}
        )
    if not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(placed, indent=2) + "\n")
        pytest.skip(f"golden captured to {GOLDEN}")
    assert placed == [tuple(x) for x in json.loads(GOLDEN.read_text())]


def test_overlay_oversize_and_missing_image_fail_closed(env):
    tmp_path, _, fixed_sha, photo_sha = env
    config = {**OVERLAY_CONFIG, "pdf_object": fixed_sha}

    wide = {**RECORD, "photo_ref": photo_sha,
            "asset_name": "AN ABSURDLY LONG ASSET IDENTIFIER THAT CANNOT FIT THE BOX"}
    problems = render_overlay_pdf(config, wide, tmp_path / "w.pdf")
    assert any(p.kind == "oversize_value" for p in problems)  # FR-014: no truncation

    ghost = {**RECORD, "photo_ref": "f" * 64}
    problems = render_overlay_pdf(config, ghost, tmp_path / "g.pdf")
    assert any(p.kind == "bad_image" for p in problems)  # FR-012a
