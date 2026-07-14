"""T015 — enrichment adds hints only: never structure, never confirmations,
never overwrites; absent/unavailable model => byte-identical no-op (FR-020)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from rmu.onboard.analyze_source import analyze
from rmu.onboard.enrich import enrich_document, sample_pages

FIX = Path("tests/fixtures/onboarding")


class FakeLLM:
    def __init__(self, payload: dict | None, available: bool = True):
        self._payload = payload
        self._available = available
        self.prompts: list[str] = []

    def available(self) -> bool:
        return self._available

    def complete_json(self, prompt: str, *, format_schema=None) -> str | None:
        self.prompts.append(prompt)
        return json.dumps(self._payload) if self._payload is not None else None


def _doc():
    return analyze([FIX / "survey_report_a.pdf"])


def test_no_llm_is_a_no_op():
    doc = _doc()
    before = copy.deepcopy(doc)
    assert enrich_document(doc, ["page text"], llm=None) == before
    assert enrich_document(doc, ["page text"], llm=FakeLLM(None, available=False)) == before
    assert "ai_assist" not in doc


def test_hints_are_additive_and_provenanced():
    doc = _doc()
    col_id = next(
        e["id"] for e in doc["elements"] if e["element_kind"] == "record_column"
    )
    llm = FakeLLM({"suggestions": [{"id": col_id, "name": "defect_reference"}]})

    enrich_document(doc, ["some text"] * 3, llm=llm)

    element = next(e for e in doc["elements"] if e["id"] == col_id)
    assert element["payload"]["suggested_name"] == "defect_reference"
    assert element["payload"]["name"]  # original heuristic name untouched
    assert element["review_state"] == "proposed"  # nothing auto-confirmed
    assert doc["ai_assist"]["mode"] == "local"
    assert doc["ai_assist"]["enrichments"] == [
        {"id": col_id, "suggested_name": "defect_reference"}
    ]


def test_malformed_model_output_dropped_wholesale():
    doc = _doc()
    before = copy.deepcopy(doc)
    bad = FakeLLM(None)
    bad.complete_json = lambda prompt, format_schema=None: "not json {"
    assert enrich_document(doc, ["x"], llm=bad) == before


def test_page_sampling_bounded():
    texts = [f"page {i} " * (i + 1) for i in range(300)]
    picked = sample_pages(texts)
    assert len(picked) <= 6
    assert picked[0] == 1 and picked[-1] == 300  # first and last always sampled
