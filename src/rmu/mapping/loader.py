"""Transform YAML parsing + validation (contracts/transform-yaml.md, research R5).

Schema validation rejects anything outside the closed grammar; loader-level
checks resolve value-map pins and compute approval preconditions (FR-007).
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from rmu.models import ValueMap

_SCHEMA_PATH = Path(__file__).parent / "schemas" / "transform-v1.json"
_schema = json.loads(_SCHEMA_PATH.read_text())


class TransformValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def parse_transform(yaml_text: str) -> dict:
    """Parse + schema-validate a transform document. Raises on any violation."""
    doc = yaml.safe_load(yaml_text)
    validator = jsonschema.Draft7Validator(_schema)
    errors = [
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in validator.iter_errors(doc)
    ]
    if errors:
        raise TransformValidationError(sorted(errors))
    return doc


def unresolved_value_maps(doc: dict, session: Session) -> list[str]:
    """Pinned (name, version) refs that do not resolve to a ValueMap row."""
    missing = []
    for field, route in doc.get("routes", {}).items():
        ref = route.get("value_map")
        if not ref:
            continue
        row = session.scalar(
            select(ValueMap).where(
                ValueMap.name == ref["name"], ValueMap.version == ref["version"]
            )
        )
        if row is None:
            missing.append(f"{field}: value_map {ref['name']}@{ref['version']} not found")
    return missing


def routed_fields(doc: dict) -> set[str]:
    """Every target field the transform fills, by any mechanism."""
    fields = set(doc.get("routes", {})) | set(doc.get("constants", {})) | set(
        doc.get("formulas", {})
    )
    for prompt in doc.get("prompts", []):
        fields.add(prompt.get("target_field") or prompt["key"])
    return fields


def missing_required(doc: dict, required_fields: list[str]) -> list[str]:
    """Required target fields with no route/constant/formula/prompt (FR-007)."""
    return sorted(set(required_fields) - routed_fields(doc))


def unreviewed_fields(doc: dict) -> list[str]:
    """Fields still at T2 (unreviewed proposal) or T3 (unmapped) — approval blockers."""
    return sorted(
        field
        for field, route in doc.get("routes", {}).items()
        if route.get("tier") in ("T2", "T3")
    )


def prompt_keys(doc: dict) -> list[str]:
    return [p["key"] for p in doc.get("prompts", []) if p.get("required", True)]
