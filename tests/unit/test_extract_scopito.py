"""T015 [TDD]: extraction ground truth from BOTH real Scopito demo PDFs (A1, A3).

The two PDFs are layout VARIANTS of profile scopito.pdf.powerline.v2020:
Distribution has an inline header label row + 'User tags' column; Transmission
stacks labels and omits 'User tags'. One profile must extract both cleanly,
with declared_counts == extracted (the FR-016 integrity signal).
"""

from pathlib import Path

import pytest

from rmu.extract.scopito_pdf_powerline import extract
from rmu.seed import profile_config

SAMPLES = Path("seed/source_samples")
VOCAB = {"1", "2", "3", "4", "5", "?"}  # A3


@pytest.fixture(scope="module")
def cfg():
    return profile_config("scopito.pdf.powerline@v2020")


@pytest.fixture(scope="module")
def distribution(cfg):
    return extract(SAMPLES / "Distribution-report.pdf", cfg)


@pytest.fixture(scope="module")
def transmission(cfg):
    return extract(SAMPLES / "Report-Transmission.pdf", cfg)


def test_distribution_header(distribution):
    h = distribution["header"]
    assert h["inspection_name"] == "Distribution demo - Lineman analysis"
    assert h["report_date"] == "Dec 2, 2020"
    assert h["declared_counts"]["annotations"] == 10
    assert h["declared_counts"]["images"] == 10


def test_distribution_findings(distribution):
    findings = distribution["findings"]
    assert len(findings) == 10
    by_id = {f["id"]: f for f in findings}
    assert set(by_id) == {
        "1703641", "1703642", "1703643", "1703644", "1703645",
        "1703646", "1703647", "1703648", "1703649", "1703650",
    }
    assert all(f["severity"] in VOCAB for f in findings)
    f44 = by_id["1703644"]
    assert f44["severity"] == "5"
    assert "Conductor Damage" in f44["issues"]
    assert "AOI-1-0127" in f44["user_tags"]
    assert "RGB" in f44["user_tags"]
    assert "burned arrestor lead" in f44["comments"]
    assert f44["page"] == 2
    assert by_id["1703646"]["severity"] == "?"  # POI record


def test_distribution_integrity_clean(distribution):
    integ = distribution["integrity"]
    assert integ["anchors_missing"] == []
    assert integ["declared_vs_extracted"] == {"declared": 10, "extracted": 10}


def test_transmission_header(transmission):
    h = transmission["header"]
    assert h["inspection_name"] == "Fjordkrydsning maste 28-31- Demo"
    assert h["report_date"] == "Jun 25, 2020"
    assert h["declared_counts"]["annotations"] == 4
    assert h["declared_counts"]["images"] == 4


def test_transmission_findings(transmission):
    findings = transmission["findings"]
    assert len(findings) == 4
    by_id = {f["id"]: f for f in findings}
    assert set(by_id) == {"871515", "871520", "1050227", "871565"}
    assert by_id["871515"]["severity"] == "4"
    assert by_id["871515"]["issues"] == ["Corrosion"]
    assert by_id["871515"]["user_tags"] == []  # no User tags column in this variant
    assert by_id["871520"]["issues"] == ["Lightning strike"]
    assert all(f["severity"] in VOCAB for f in findings)


def test_transmission_integrity_clean(transmission):
    integ = transmission["integrity"]
    assert integ["anchors_missing"] == []
    assert integ["declared_vs_extracted"] == {"declared": 4, "extracted": 4}


def test_contract_shape(distribution, cfg):
    assert distribution["schema"] == "rmu.normalized/1"
    assert distribution["profile"] == "scopito.pdf.powerline@v2020"
    assert len(distribution["source_sha256"]) == 64
    assert isinstance(distribution["assets"], list)
    assert len(distribution["assets"]) == 10  # one image detail page per annotation
