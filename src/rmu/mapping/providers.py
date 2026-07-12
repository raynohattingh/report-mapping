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
    # Feature 002 provenance (FR-013): who produced this proposal and with what
    # asset — e.g. provider="local", asset="ollama:qwen3:4b". None for legacy paths.
    provider: str | None = None
    asset: str | None = None


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


@dataclass
class AssistBundle:
    """Output of one local assist pass (feature 002): proposals plus the stats
    the session persists (assets used, degraded tiers, shown/dropped counts,
    per-source-field rankings). `mode`/`client`/`generated_at` are added by the
    CLI, which knows them; the provider fills the rest."""

    proposals: list[Proposal]
    stats: dict


def _observed_values(normalized: dict) -> dict[str, set[str]]:
    """Every value actually seen per source path, for the gate's value check."""
    obs: dict[str, set[str]] = {}
    groups = (("header", [normalized["header"]]), ("finding", normalized["findings"]))
    for scope, items in groups:
        for item in items:
            for key, value in item.items():
                path = f"{scope}.{key}"
                bucket = obs.setdefault(path, set())
                if isinstance(value, list):
                    bucket.update(str(x) for x in value)
                elif isinstance(value, (str, int, float)):
                    bucket.add(str(value))
    return obs


def _local_prompt(sample: dict, target_fields: list[str], defect_codes: list[dict]) -> str:
    codes = [{"code": c["code"], "label": c["label"]} for c in defect_codes]
    return (
        "You propose a field mapping for a drone-inspection report converter.\n"
        f"Source exemplar (extracted):\n{json.dumps(sample, indent=1)}\n\n"
        f"Target fields to fill: {target_fields}\n"
        f"Target defect-code vocabulary: {json.dumps(codes)}\n\n"
        "Return ONLY a JSON array. Each element maps one target field: "
        "{target_field, from_path (header.<key> or finding.<key>), rationale "
        "(one short line), and — only for a vocabulary/scale/units/date conversion "
        "(e.g. severity 1-5 -> priority, issue label -> defect code) — value_map_name "
        "plus suggested_entries ([{source_value, target_value}]) drawn from values "
        "present in the exemplar."
    )


class LocalProvider:
    """Local assist (D8 tiers 1+2). Composes in-process embeddings (ranking) and
    an optional loopback LLM (value-map/route proposals) behind the strict gate,
    degrading per tier (FR-011). Constructed with an `rmu.ai.config.AiConfig`."""

    name = "local"

    def __init__(self, config):
        self.config = config
        self._embeddings = None
        self._llm = None
        self.last_bundle: AssistBundle | None = None
        if config is not None:
            from rmu.ai.embeddings import EmbeddingBackend
            from rmu.ai.llm_local import LocalLLM

            self._embeddings = EmbeddingBackend(config.embedding_model)
            self._llm = LocalLLM(config.ollama_host, config.llm_model, config.timeout_seconds)

    def propose(self, normalized, required_fields, defect_codes):
        """Protocol path: rank/propose against the required fields only."""
        targets = {f: f for f in required_fields}
        return self.assist(normalized, targets, list(required_fields), defect_codes).proposals

    def assist(
        self,
        normalized: dict,
        target_descriptors: dict[str, str],
        target_fields: list[str],
        defect_codes: list[dict],
    ) -> AssistBundle:
        from rmu.ai import ranking, validation
        from rmu.mapping.session import source_inventory

        assets: dict[str, str] = {}
        degraded: list[str] = []
        rankings: dict[str, list[dict]] = {}
        inventory = source_inventory(normalized)

        # Tier 1 — in-process embeddings: rank candidate target fields per source.
        if self._embeddings is not None and self._embeddings.available():
            assets["embedding"] = f"fastembed:{self.config.embedding_model}"
            sources = {
                f"{scope}.{key}": ranking.descriptor_for_source(f"{scope}.{key}")
                for scope in ("header", "finding")
                for key in inventory.get(scope, {})
            }
            rankings = ranking.rank_candidates(sources, target_descriptors, self._embeddings)
        else:
            degraded.append("embedding")

        # Tier 2 — optional loopback LLM: proposals through the strict gate.
        proposals: list[Proposal] = []
        dropped = {"schema": 0, "unknown_field": 0, "unknown_value": 0}
        if self._llm is not None and self._llm.available():
            asset = f"ollama:{self.config.llm_model}"
            assets["llm"] = asset
            sample = {"header": normalized["header"], "findings": normalized["findings"][:5]}
            raw = self._llm.complete_json(_local_prompt(sample, target_fields, defect_codes))
            if raw is None:
                degraded.append("llm")
            else:
                proposals, dropped = validation.gate_proposals(
                    raw,
                    source_inventory=inventory,
                    target_fields=set(target_fields),
                    observed_values=_observed_values(normalized),
                )
                for p in proposals:
                    p.provider = "local"
                    p.asset = asset
        else:
            degraded.append("llm")

        bundle = AssistBundle(
            proposals=proposals,
            stats={
                "assets": assets,
                "degraded": degraded,
                "shown": len(proposals),
                "dropped": dropped,
                "rankings": rankings,
            },
        )
        self.last_bundle = bundle
        return bundle


def get_provider(
    mode: str,
    *,
    stub: bool = False,
    client: str | None = None,
    config=None,
) -> ProposalProvider:
    """Construct the proposal provider for an assistance mode (feature 002, D8).

    `mode` is one of none|local|external (resolved upstream). `stub=True` is a
    test-only override. `config` is an `rmu.ai.config.AiConfig`; `client` gates
    external mode (consent enforced in the CLI, contracts/cli-ai.md).
    """
    if stub:
        return StubProvider()
    if mode == "none":
        return NullProvider()
    if mode == "local":
        return LocalProvider(config)
    if mode == "external":
        return AnthropicProvider()
    raise ValueError(f"unknown assistance mode {mode!r}")
