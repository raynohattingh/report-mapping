"""T014 — FR-001b: no detected structure => diagnosis + hand-fillable skeleton,
never a dead end."""

from __future__ import annotations

from pathlib import Path

from rmu.onboard.analyze_source import analyze
from rmu.onboard.schemas import validate_proposal
from rmu.onboard.skeleton import attach_diagnosis, is_structureless

FIX = Path("tests/fixtures/onboarding")


def test_prose_report_takes_the_skeleton_path():
    document = analyze([FIX / "prose_report.pdf"])
    assert is_structureless(document)

    attach_diagnosis(document)
    validate_proposal(document)  # still a valid, reviewable proposal
    assert document["diagnosis"]["searched"]  # what analysis looked for
    assert "hand" in document["diagnosis"]["notes"]  # points at manual authoring


def test_structured_report_is_not_structureless():
    assert not is_structureless(analyze([FIX / "survey_report_a.pdf"]))
