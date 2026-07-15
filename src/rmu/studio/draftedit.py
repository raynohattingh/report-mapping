"""Studio draft-transform edits (FR-013/FR-013a/FR-014, US3 mechanisms).

Every mutation: split banner → edit the parsed doc → canonical render →
schema-validate BEFORE writing (mapping.loader.parse_transform) → write under
the DraftLease (FR-005). The result is byte-identical to the same edit made by
any script over split_draft/render_draft — the studio adds no dialect.

Tier derivation (FR-013a, per design §7 which takes precedence over the spec's
parenthetical): a route is T1 when it translates vocabulary through a value
map (validated), T0 when it is a direct deterministic copy; constants and
formulas are inherently T0 mechanisms. The analyst never hand-picks a tier in
the studio; it recomputes whenever the mechanism changes.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from rmu.mapping.loader import parse_transform
from rmu.mapping.session import render_draft, split_draft
from rmu.studio.concurrency import DraftLease


class RouteEditError(ValueError):
    """A route edit that cannot apply (unknown field, wrong state)."""


def derived_tier(route: dict) -> str:
    return "T1" if route.get("value_map") else "T0"


def apply_doc_edit(
    lease: DraftLease,
    draft_path: Path,
    base_hash: str,
    mutate: Callable[[dict], None],
    *,
    overwrite: bool = False,
) -> dict:
    """Mutate the draft document; validate; write. Returns the new doc."""

    def edit(text: str) -> str:
        banner, doc = split_draft(text)
        mutate(doc)
        new_text = render_draft(banner, doc)
        parse_transform(new_text)  # reject anything outside the grammar (FR-013)
        return new_text

    new_text = lease.apply_edit(draft_path, base_hash, edit, overwrite=overwrite)
    return parse_transform(new_text)


# --- route mutations (the decision vocabulary maps at approval time:
#     accept→accepted, reject→rejected, reroute→edited, create→manual) -------

def create_route(doc: dict, field: str, from_path: str) -> None:
    if field in doc.get("routes", {}):
        raise RouteEditError(f"field '{field}' already has a route — re-route it instead")
    route = {"from": from_path, "tier": "T0"}
    route["tier"] = derived_tier(route)
    doc.setdefault("routes", {})[field] = route


def accept_route(doc: dict, field: str) -> None:
    route = doc.get("routes", {}).get(field)
    if route is None:
        raise RouteEditError(f"no route for field '{field}'")
    if route.get("tier") != "T2":
        raise RouteEditError(f"field '{field}' is not a pending proposal (tier "
                             f"{route.get('tier')})")
    route["tier"] = derived_tier(route)  # the ONLY path to an approvable state


def reject_route(doc: dict, field: str) -> None:
    if field not in doc.get("routes", {}):
        raise RouteEditError(f"no route for field '{field}'")
    del doc["routes"][field]


def reroute(doc: dict, field: str, from_path: str) -> None:
    route = doc.get("routes", {}).get(field)
    if route is None:
        raise RouteEditError(f"no route for field '{field}'")
    route["from"] = from_path
    route["tier"] = derived_tier(route)


def delete_route(doc: dict, field: str) -> None:
    reject_route(doc, field)


# --- link-level mechanisms (US3, FR-021/FR-022) ------------------------------

def pin_value_map(doc: dict, field: str, name: str, version: int) -> None:
    route = doc.get("routes", {}).get(field)
    if route is None:
        raise RouteEditError(f"no route for field '{field}'")
    route["value_map"] = {"name": name, "version": version}
    if route.get("tier") in ("T0", "T1"):
        route["tier"] = derived_tier(route)  # mechanism changed → recompute


def set_constant(doc: dict, field: str, value: str) -> None:
    doc.get("routes", {}).pop(field, None)
    doc.setdefault("constants", {})[field] = value


def set_formula(doc: dict, field: str, spec: dict) -> None:
    doc.get("routes", {}).pop(field, None)
    doc.setdefault("formulas", {})[field] = spec


def set_prompt(doc: dict, field: str, key: str, label: str, required: bool) -> None:
    doc.get("routes", {}).pop(field, None)
    prompts = [p for p in doc.get("prompts", []) if p["key"] != key]
    prompt = {"key": key, "label": label, "required": required}
    if field and field != key:
        prompt["target_field"] = field
    prompts.append(prompt)
    doc["prompts"] = sorted(prompts, key=lambda p: p["key"])
