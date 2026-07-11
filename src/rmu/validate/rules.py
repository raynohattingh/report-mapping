"""Validate stage: enforce TargetTemplate.validation_rules on converted rows
(design §4, FR-001; convergence T050).

Vocabulary legality is the guard against the product's worst failure mode —
semantically-wrong-but-structurally-valid output (Constitution V): a value-map
entry whose target falls outside the registered vocabulary must surface as an
exception, never ship silently. Vocabularies are data: inline lists or a CSV
reference (e.g. seed/defect_codes_v1.csv), never hardcoded (Constitution IV).
"""

from __future__ import annotations

import csv
from pathlib import Path

from rmu.config import REPO_ROOT


def load_vocabularies(validation_rules: dict) -> dict[str, set[str]]:
    """field -> allowed value set, from inline `vocabulary` or `vocabulary_csv`."""
    vocabularies: dict[str, set[str]] = {}
    for field, rule in validation_rules.items():
        if "vocabulary" in rule:
            vocabularies[field] = {str(v) for v in rule["vocabulary"]}
        elif "vocabulary_csv" in rule:
            path = Path(rule["vocabulary_csv"])
            if not path.is_absolute():
                path = REPO_ROOT / path
            column = rule.get("code_column", "code")
            with open(path, newline="", encoding="utf-8") as fh:
                vocabularies[field] = {row[column] for row in csv.DictReader(fh)}
    return vocabularies


def validate_rows(
    rows: list[dict], vocabularies: dict[str, set[str]], record_key: str = "finding_id"
) -> tuple[list[dict], list[dict]]:
    """Split rows into (legal, exceptions). An illegal value removes the whole
    row from output — reported, never shipped (FR-012 discipline)."""
    valid: list[dict] = []
    problems: list[dict] = []
    for row in rows:
        violations = [
            (field, row[field])
            for field, allowed in vocabularies.items()
            if field in row and str(row[field]) not in allowed
        ]
        if not violations:
            valid.append(row)
            continue
        for field, value in violations:
            problems.append({
                "record_ref": str(row.get(record_key, "?")),
                "kind": "invalid_value",
                "detail": {
                    "field": field,
                    "value": str(value),
                    "reason": (
                        f"value {value!r} for '{field}' is outside the template's "
                        "registered vocabulary"
                    ),
                    "suggestion": (
                        "fix the value-map entry (new version) or extend the "
                        "template's vocabulary as data"
                    ),
                },
            })
    return valid, problems
