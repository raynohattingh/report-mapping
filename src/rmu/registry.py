"""Registry lookups shared by CLI commands (thin, read-only helpers)."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from rmu import store
from rmu.models import SourceProfile, TargetTemplate, ValueMap


def get_profile(session: Session, ref: str) -> SourceProfile:
    key, _, sv = ref.partition("@")
    row = session.scalar(
        select(SourceProfile).where(
            SourceProfile.key == key, SourceProfile.structural_version == sv
        )
    )
    if row is None:
        raise LookupError(f"unknown source profile '{ref}' (run `rmu seed load`?)")
    return row


def get_template(session: Session, ref: str) -> TargetTemplate:
    name, _, ver = ref.partition("@")
    row = session.scalar(
        select(TargetTemplate).where(
            TargetTemplate.name == name, TargetTemplate.version == int(ver or 1)
        )
    )
    if row is None:
        raise LookupError(f"unknown target template '{ref}' (run `rmu seed load`?)")
    return row


def get_template_by_id(session: Session, template_id: int) -> TargetTemplate:
    row = session.get(TargetTemplate, template_id)
    if row is None:
        raise LookupError(f"no target template id={template_id}")
    return row


def template_meta(template: TargetTemplate) -> dict:
    """template.json content (kind, columns, ...) from the content store."""
    return json.loads(store.get_bytes(template.template_files["template.json"]))


def required_fields(template: TargetTemplate) -> list[str]:
    return list(template.required_schema.get("required", []))


def load_value_maps(session: Session, doc: dict) -> dict[tuple[str, int], list[dict]]:
    """Load every value map the transform pins, keyed (name, version)."""
    pins = {
        (ref["name"], ref["version"])
        for route in doc.get("routes", {}).values()
        if (ref := route.get("value_map"))
    }
    loaded: dict[tuple[str, int], list[dict]] = {}
    for name, version in pins:
        row = session.scalar(
            select(ValueMap).where(ValueMap.name == name, ValueMap.version == version)
        )
        if row is not None:
            loaded[(name, version)] = row.entries
    return loaded


def next_value_map_version(session: Session, name: str) -> int:
    versions = session.scalars(select(ValueMap.version).where(ValueMap.name == name)).all()
    return max(versions, default=0) + 1
