"""HIL mapping session (design §6): draft building, lineage, decisions.

The session is the ONLY place AI proposals exist, and they enter the draft at
tier T2 — schema-valid but approval-blocked until the human decides (FR-005/007).
Every proposal and every decision is persisted with timestamps (FR-021).
"""

from __future__ import annotations

import datetime
from dataclasses import asdict

import yaml

from rmu.mapping.providers import Proposal


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")


def source_inventory(normalized: dict) -> dict:
    """What the exemplar offers: header keys + finding keys with sample values."""
    header = normalized["header"]
    sample = normalized["findings"][0] if normalized["findings"] else {}
    return {
        "header": {k: v for k, v in header.items() if k != "declared_counts"},
        "finding": {k: sample.get(k) for k in
                    ("id", "severity", "user_tags", "issues", "comments", "page")},
    }


def build_draft(
    normalized: dict,
    template_name: str,
    template_version: int,
    profile_key_at_version: str,
    required_fields: list[str],
    proposals: list[Proposal],
    rankings: dict[str, list[dict]] | None = None,
) -> str:
    """Draft transform YAML: proposals at T2, remaining required fields at T3.

    The emitted document is schema-valid from the start so every edit loop can
    validate; T3 placeholders keep it approval-blocked until resolved. When
    embedding rankings are supplied they are added as candidate-route comments —
    a shortlist to pick from, never a decision (Principle V, FR-005).
    """
    routes: dict = {}
    for p in proposals:
        route: dict = {"from": p.from_path, "tier": "T2", "rationale": p.rationale}
        if p.value_map_name:
            route["value_map"] = {"name": p.value_map_name, "version": 1}
        routes[p.target_field] = route
    for field in required_fields:
        if field not in routes:
            routes[field] = {
                "from": "?",
                "tier": "T3",
                "rationale": "unmapped: replace with a route, constant, formula or prompt",
            }

    doc = {
        "meta": {
            "source_profile": profile_key_at_version,
            "target_template": f"{template_name}@{template_version}",
            "version": 1,
            "parent_version": None,
        },
        "routes": routes,
        "constants": {},
        "formulas": {},
        "prompts": [],
        "exceptions": {"unmapped_optional": "skip"},
    }

    inventory = yaml.safe_dump(
        source_inventory(normalized), sort_keys=True, allow_unicode=True
    )
    banner = (
        "# RMU draft transform - edit, validate with `rmu map review`, approve with"
        " `rmu map approve`.\n"
        "# Tiers: T0/T1 human-confirmed, T2 AI-proposed (decide!), T3 unmapped"
        " (route/constant/formula/prompt required).\n"
        "# Exemplar source inventory:\n"
        + "".join(f"#   {line}\n" for line in inventory.splitlines())
    )
    if rankings:
        banner += (
            "# AI candidate target fields (embedding similarity — a shortlist to pick"
            " from, NOT a decision):\n"
        )
        for source_key in sorted(rankings):
            shortlist = ", ".join(
                f"{c['target_field']} ({c['score']:.2f})" for c in rankings[source_key]
            )
            banner += f"#   {source_key} resembles: {shortlist}\n"
    return banner + yaml.safe_dump(doc, sort_keys=True, allow_unicode=True)


def proposals_for_lineage(proposals: list[Proposal]) -> list[dict]:
    at = _now_iso()
    return [{**asdict(p), "at": at} for p in proposals]


def starter_value_maps(proposals: list[Proposal]) -> dict[str, list[dict]]:
    """Suggested value-map entries emitted as starter files for human review.

    Nothing enters the ValueMap registry until the human explicitly runs
    `rmu valuemap create` on the (edited) starter (Constitution V).
    """
    return {
        p.value_map_name: p.suggested_entries
        for p in proposals
        if p.value_map_name and p.suggested_entries
    }


def compute_decisions(proposals: list[dict], final_doc: dict) -> list[dict]:
    """Diff proposals against the approved document -> explicit decision log."""
    at = _now_iso()
    decisions: list[dict] = []
    routes = final_doc.get("routes", {})
    proposed_fields = {p["target_field"]: p for p in proposals}

    for field, proposal in proposed_fields.items():
        in_constants = field in final_doc.get("constants", {})
        in_formulas = field in final_doc.get("formulas", {})
        if field not in routes and not in_constants and not in_formulas:
            decisions.append({"target_field": field, "action": "rejected", "at": at,
                              "detail": "proposal removed from draft"})
            continue
        route = routes.get(field)
        if route is None:
            decisions.append({"target_field": field, "action": "edited", "at": at,
                              "detail": "replaced by constant/formula"})
        elif route["from"] == proposal["from_path"]:
            decisions.append({"target_field": field, "action": "accepted", "at": at,
                              "detail": f"tier {route['tier']}"})
        else:
            decisions.append({"target_field": field, "action": "edited", "at": at,
                              "detail": f"route changed to {route['from']}"})

    for field, route in routes.items():
        if field not in proposed_fields:
            decisions.append({"target_field": field, "action": "manual", "at": at,
                              "detail": f"human-authored route from {route['from']}"})
    for field in final_doc.get("constants", {}):
        if field not in proposed_fields:
            decisions.append({"target_field": field, "action": "manual", "at": at,
                              "detail": "human-authored constant"})
    for field in final_doc.get("formulas", {}):
        if field not in proposed_fields:
            decisions.append({"target_field": field, "action": "manual", "at": at,
                              "detail": "human-authored formula"})
    for prompt in final_doc.get("prompts", []):
        decisions.append({"target_field": prompt.get("target_field") or prompt["key"],
                          "action": "manual", "at": at,
                          "detail": f"per-batch prompt '{prompt['key']}'"})
    return sorted(decisions, key=lambda d: d["target_field"])
