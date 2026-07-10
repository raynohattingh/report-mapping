from pathlib import Path
from types import SimpleNamespace

import pytest

from rmu.detect import detect_profile
from rmu.seed import profile_config

SAMPLES = Path("seed/source_samples")


@pytest.fixture(scope="module")
def scopito_profile():
    cfg = profile_config("scopito.pdf.powerline@v2020")
    return SimpleNamespace(status="active", fingerprint=cfg["fingerprint"], key=cfg["key"])


@pytest.fixture(scope="module")
def unknown_pdf(tmp_path_factory):
    """A structurally alien PDF: valid file, none of the anchors (FR-002)."""
    from reportlab.pdfgen import canvas

    path = tmp_path_factory.mktemp("unknown") / "unknown.pdf"
    c = canvas.Canvas(str(path))
    c.drawString(72, 720, "Quarterly Financial Statement")
    c.drawString(72, 700, "Totally unrelated document")
    c.save()
    return path


def test_both_real_pdfs_detected(scopito_profile):
    for name in ["Distribution-report.pdf", "Report-Transmission.pdf"]:
        assert detect_profile(SAMPLES / name, [scopito_profile]) is scopito_profile, name


def test_unknown_document_routes_to_none(scopito_profile, unknown_pdf):
    assert detect_profile(unknown_pdf, [scopito_profile]) is None


def test_inactive_profile_never_matches(scopito_profile):
    inactive = SimpleNamespace(
        status="superseded", fingerprint=scopito_profile.fingerprint, key=scopito_profile.key
    )
    assert detect_profile(SAMPLES / "Distribution-report.pdf", [inactive]) is None
