"""T012 — NEVER CUT (Constitution VIII): recipe-driven extraction is
deterministic — identical input + identical recipe => identical
NormalizedRecords, including content-addressed image refs (FR-004)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rmu.extract.recipe_pdf import extract
from tests.unit.test_recipe_pdf import RECIPE

FIX = Path("tests/fixtures/onboarding")


@pytest.fixture(autouse=True)
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))


def test_reextraction_is_byte_identical():
    runs = [
        json.dumps(extract(FIX / "survey_report_a.pdf", RECIPE), sort_keys=True)
        for _ in range(2)
    ]
    assert runs[0] == runs[1]
