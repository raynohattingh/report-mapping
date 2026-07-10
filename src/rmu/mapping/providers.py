"""Proposal providers (research R6). AI lives HERE and only here (A6,
Constitution VII): nothing under apply/, detect/, extract/, validate/ or
render/ may import this module. Enforced by tests/invariants/test_no_ai_in_apply.py.

Every proposal enters the draft at tier T2 — visually distinct, approval-blocked
until an explicit human decision (FR-005, design §7).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Proposal:
    target_field: str
    from_path: str
    rationale: str
    tier: str = "T2"  # always T2 until a human decides (Constitution V)
    value_map_name: str | None = None
    suggested_entries: list[dict] = field(default_factory=list)


class ProposalProvider(Protocol):
    name: str

    def propose(
        self, normalized: dict, required_fields: list[str], defect_codes: list[dict]
    ) -> list[Proposal]: ...


class NullProvider:
    """--no-ai mode (D3 degradation floor): zero proposals, pure manual session."""

    name = "null"

    def propose(self, normalized, required_fields, defect_codes):  # noqa: ARG002
        return []


class StubProvider:
    """Deterministic canned proposals for tests — no network, ever."""

    name = "stub"

    def propose(self, normalized, required_fields, defect_codes):
        severities = sorted({f["severity"] for f in normalized["findings"]})
        issues = sorted({i for f in normalized["findings"] for i in f["issues"]})
        fallback_code = defect_codes[0]["code"] if defect_codes else ""
        proposals = [
            Proposal("finding_id", "finding.id", "source annotation id is the natural key"),
            Proposal("asset_name", "header.inspection_name",
                     "inspection name identifies the asset"),
            Proposal("inspection_date", "header.report_date", "report date is the inspection date"),
            Proposal("source_severity", "finding.severity", "verbatim source severity 1-5/?"),
            Proposal(
                "priority",
                "finding.severity",
                "severity 1-5/? converts to priority vocabulary",
                value_map_name="severity_to_priority",
                suggested_entries=[
                    {"source_value": s,
                     "target_value": {"5": "P1", "4": "P2", "3": "P3", "2": "P4",
                                      "1": "P4", "?": "POI"}.get(s, "POI"),
                     "provenance": "ai-accepted",
                     "note": "stub severity->priority suggestion"}
                    for s in severities
                ],
            ),
            Proposal(
                "defect_code",
                "finding.issues",
                "issue labels convert to the interim defect-code vocabulary",
                value_map_name="issue_to_defect_code",
                suggested_entries=[
                    {"source_value": issue, "target_value": fallback_code,
                     "provenance": "ai-accepted",
                     "note": "stub suggestion - human must review the code"}
                    for issue in issues
                ],
            ),
            Proposal("comments", "finding.comments", "free-text comments carry over"),
            Proposal("user_tags", "finding.user_tags", "tags carry over joined"),
            Proposal("source_page", "finding.page", "source page reference"),
        ]
        return [p for p in proposals if p.target_field in set(required_fields) | {
            "comments", "user_tags", "source_page"}]


class AnthropicProvider:
    """Claude-backed proposals — mapping session ONLY, demo/synthetic data only
    until client consent exists (A6, FR-020). Never constructed with --no-ai."""

    name = "anthropic"
    MODEL = "claude-fable-5"

    def __init__(self, api_key: str | None = None):
        import anthropic  # deferred: importable only on this path (R6)

        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def propose(self, normalized, required_fields, defect_codes):
        sample = {
            "header": normalized["header"],
            "findings": normalized["findings"][:5],
        }
        codes = [{"code": c["code"], "label": c["label"]} for c in defect_codes]
        prompt = (
            "You are proposing a field mapping for a drone-inspection report converter.\n"
            f"Source exemplar (extracted):\n{json.dumps(sample, indent=1)}\n\n"
            f"Required target fields: {required_fields}\n"
            f"Target defect-code vocabulary: {json.dumps(codes)}\n\n"
            "Propose one route per target field as a JSON array of objects with keys: "
            "target_field, from_path (header.<key> or finding.<key>), rationale "
            "(one line), and optionally value_map_name plus suggested_entries "
            "([{source_value, target_value}]) when a vocabulary conversion is needed "
            "(severity->priority, issue label->defect code). Reply with ONLY the JSON array."
        )
        message = self._client.messages.create(
            model=self.MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(block.text for block in message.content if block.type == "text")
        items = json.loads(raw)
        return [
            Proposal(
                target_field=i["target_field"],
                from_path=i["from_path"],
                rationale=i.get("rationale", ""),
                value_map_name=i.get("value_map_name"),
                suggested_entries=[
                    {**e, "provenance": "ai-accepted", "note": "AI suggestion pending review"}
                    for e in i.get("suggested_entries", [])
                ],
            )
            for i in items
        ]


def get_provider(
    no_ai: bool, stub: bool = False
) -> NullProvider | StubProvider | AnthropicProvider:
    if no_ai:
        return NullProvider()
    if stub:
        return StubProvider()
    return AnthropicProvider()
