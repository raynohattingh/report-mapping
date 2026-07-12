"""T018/T019 (SC-002, FR-012): embedding candidate ranking places the confirmed
target in the top 3 for >= 90% of routed source fields, deterministically.

Uses ONLY bundled data: the two committed example transforms' confirmed routes
(tests/fixtures/ranking_ground_truth.yaml) and the seeded template field labels.
Skips cleanly if the embedding cache is not warmed — the T031 gate requires a
non-skipped run on the reference machine before the feature is declared done.
"""

import json
from pathlib import Path

import pytest
import yaml

from rmu.ai.embeddings import EmbeddingBackend
from rmu.ai.ranking import descriptor_for_source, descriptor_for_target, rank_candidates
from rmu.config import REPO_ROOT

MODEL = "BAAI/bge-small-en-v1.5"
GROUND_TRUTH = Path(__file__).parent.parent / "fixtures" / "ranking_ground_truth.yaml"

pytestmark = pytest.mark.skipif(
    not EmbeddingBackend(MODEL).available(),
    reason="bge-small cache not warmed (run `rmu ai setup`)",
)


def _template_schema(template: str) -> dict:
    return json.loads((REPO_ROOT / "templates" / template / "schema.json").read_text())


def _target_fields(schema: dict) -> list[str]:
    return list(schema.get("required", [])) + list(schema.get("optional", [])) + list(
        schema.get("finding_fields", [])
    )


def _rank_case(backend, case):
    schema = _template_schema(case["template"])
    labels = schema.get("field_labels", {})
    targets = {t: descriptor_for_target(t, labels.get(t)) for t in _target_fields(schema)}
    sources = {
        r["from"]: descriptor_for_source(r["from"]) for r in case["routes"]
    }
    return rank_candidates(sources, targets, backend, top_k=3)


def test_top3_hit_rate_meets_90_percent():
    data = yaml.safe_load(GROUND_TRUTH.read_text())
    backend = EmbeddingBackend(MODEL)

    total = 0
    hits = 0
    misses = []
    for case in data["cases"]:
        ranked = _rank_case(backend, case)
        for route in case["routes"]:
            total += 1
            top3 = [c["target_field"] for c in ranked[route["from"]]]
            if route["target"] in top3:
                hits += 1
            else:
                misses.append((case["template"], route["from"], route["target"], top3))

    assert total == data["expected_route_count"], (
        f"ground truth drift: {total} routes, expected {data['expected_route_count']}"
    )
    rate = hits / total
    assert rate >= 0.90, f"top-3 hit rate {hits}/{total} = {rate:.0%}; misses: {misses}"


def test_ranking_is_deterministic():
    data = yaml.safe_load(GROUND_TRUTH.read_text())
    backend = EmbeddingBackend(MODEL)
    case = data["cases"][0]
    first = _rank_case(backend, case)
    second = _rank_case(backend, case)
    assert first == second


def test_lexical_tie_break_on_equal_scores():
    # Two targets with identical descriptors must order lexically by field name.
    backend = EmbeddingBackend(MODEL)
    ranked = rank_candidates(
        {"finding.thing": "thing"},
        {"z_field": "same text", "a_field": "same text"},
        backend,
        top_k=2,
    )
    order = [c["target_field"] for c in ranked["finding.thing"]]
    assert order == ["a_field", "z_field"]
