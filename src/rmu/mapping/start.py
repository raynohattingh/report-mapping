"""Session initiation/regeneration/abandonment — the single write path (D6).

Extracted from the `rmu map start` / `rmu map regenerate` Typer bodies for
feature 004 (research.md R4): the CLI and the studio both call these, so their
artifacts are identical by construction (FR-001/FR-036). NO behavior change
from the CLI originals — refusal messages are carried verbatim on typed
exceptions and the callers map them to exit codes / HTTP statuses.
"""

from __future__ import annotations

import datetime
import importlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from rmu import store as blobstore
from rmu.ai.config import AiConfigError, has_consent, load_ai_config, resolve_mode
from rmu.config import store_root
from rmu.detect import detect_profile
from rmu.mapping import session as sess
from rmu.mapping.providers import get_provider
from rmu.models import MappingSession, SourceDocument, SourceProfile
from rmu.registry import get_profile, get_template, get_template_by_id, required_fields
from rmu.seed import load_defect_codes, profile_config


class StartRefused(RuntimeError):
    """A start/regenerate refusal; `message` is the CLI's exact text.

    exit_code matches the CLI contract: 1 config error, 2 blocked, 3 approval
    precondition, 4 consent refused.
    """

    def __init__(self, message: str, exit_code: int):
        self.message = message
        self.exit_code = exit_code
        super().__init__(message)


@dataclass
class StartResult:
    session_id: int
    mode: str
    draft_path: Path
    starter_paths: dict[str, Path] = field(default_factory=dict)
    assist_stats: dict | None = None
    shown: int = 0  # proposals in this generation (regenerate CLI echo)


def _noop(_message: str) -> None:  # progress callback default
    return None


def generate_assist(mode, session_mode, *, stub_ai, provider, normalized,
                    template_row, defect_codes, client,
                    notify: Callable[[str], None] = _noop):
    """Assist generation shared by start and regenerate (moved from cli.py).

    Returns (proposals, assist_stats); `notify` receives the progress /
    degradation messages the CLI printed to stderr (FR-011)."""
    generated_at = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")

    if mode == "local" and not stub_ai:
        from rmu.ai.ranking import descriptor_for_target

        schema = template_row.required_schema
        labels = schema.get("field_labels", {})
        target_fields_all = (
            list(schema.get("required", []))
            + list(schema.get("optional", []))
            + list(schema.get("finding_fields", []))
        )
        target_desc = {t: descriptor_for_target(t, labels.get(t)) for t in target_fields_all}
        notify("assist: ranking candidate target fields…")
        bundle = provider.assist(normalized, target_desc, target_fields_all, defect_codes)
        if "embedding" in bundle.stats["degraded"]:
            notify("assist: embeddings unavailable — no candidate ranking "
                   "(run `rmu ai setup`)")
        if "llm" in bundle.stats["degraded"]:
            notify("assist: local LLM unavailable — no value-map proposals "
                   "(run `rmu ai setup`)")
        else:
            notify("assist: proposing value maps…")
        stats = {"mode": session_mode, "client": client,
                 "generated_at": generated_at, **bundle.stats}
        return bundle.proposals, stats

    proposals = provider.propose(normalized, required_fields(template_row), defect_codes)
    if session_mode == "manual":
        return proposals, None
    stats = {
        "mode": session_mode, "client": client, "generated_at": generated_at,
        "assets": {}, "degraded": [], "shown": len(proposals),
        "dropped": {"schema": 0, "unknown_field": 0, "unknown_value": 0}, "rankings": {},
    }
    return proposals, stats


def _resolve_assist_mode(assist: str | None, no_ai: bool, cfg) -> str:
    if no_ai:
        return "none"
    return resolve_mode(assist, os.environ.get("RMU_ASSIST_MODE"), cfg)


def _check_external_consent(cfg, client: str | None) -> None:
    if not client:
        raise StartRefused(
            "refused: --assist external requires --client <id> "
            "(consent is per-client, FR-004)", 4)
    if not has_consent(cfg, client):
        raise StartRefused(
            f"refused: no external-API consent recorded for client "
            f"{client!r}; record it with `rmu ai consent grant "
            f"--client {client} --by <owner>`", 4)


def start_session(
    s: Session,
    profile_ref: str,
    template_ref: str,
    exemplar_path: Path,
    *,
    assist: str | None = None,
    client: str | None = None,
    no_ai: bool = False,
    stub_ai: bool = False,
    notify: Callable[[str], None] = _noop,
) -> StartResult:
    """The full `rmu map start` body (US1, design §6). Raises StartRefused /
    LookupError exactly where the CLI printed-and-exited."""
    profile_row = get_profile(s, profile_ref)
    template_row = get_template(s, template_ref)

    detected = detect_profile(exemplar_path, list(s.scalars(select(SourceProfile))))
    if detected is None or detected.id != profile_row.id:
        raise StartRefused(
            "blocked: exemplar does not match the requested profile fingerprint", 2)

    cfg_profile = profile_config(profile_ref)
    extractor = importlib.import_module(profile_row.extractor_ref)
    normalized = extractor.extract(exemplar_path, cfg_profile)
    blocked, reason = extractor.is_blocked(normalized)
    if blocked:
        raise StartRefused(f"blocked: exemplar failed integrity: {reason}", 2)

    extraction_ref = blobstore.put_bytes(
        json.dumps(normalized, sort_keys=True).encode("utf-8")
    )
    # Content-address the exemplar itself so any surface can re-serve it
    # (FR-036: an uploaded exemplar and a path-based start are identical).
    blobstore.put_file(exemplar_path)
    doc_row = s.scalar(
        select(SourceDocument).where(
            SourceDocument.sha256 == normalized["source_sha256"]
        )
    )
    if doc_row is None:
        doc_row = SourceDocument(
            sha256=normalized["source_sha256"],
            original_filename=exemplar_path.name,
            profile_id=profile_row.id,
            received_at=datetime.datetime.now(datetime.UTC),
            extraction_ref=extraction_ref,
        )
        s.add(doc_row)
        s.flush()

    try:
        cfg = load_ai_config(store_root())
        mode = _resolve_assist_mode(assist, no_ai, cfg)
    except AiConfigError as err:
        raise StartRefused(f"error: {err}", 1) from err

    # External mode is consent-gated (FR-004): refuse without a recorded
    # per-client entry (exit 4). Client identity is explicit, never inferred.
    if mode == "external":
        _check_external_consent(cfg, client)

    session_mode = "manual" if mode == "none" else ("stub" if stub_ai else mode)
    provider = get_provider(mode, stub=stub_ai, client=client, config=cfg)
    proposals, assist_stats = generate_assist(
        mode, session_mode, stub_ai=stub_ai, provider=provider, normalized=normalized,
        template_row=template_row, defect_codes=load_defect_codes(), client=client,
        notify=notify,
    )

    ms = MappingSession(
        source_profile_id=profile_row.id,
        target_template_id=template_row.id,
        exemplar_document_id=doc_row.id,
        mode=session_mode,
        proposals=sess.proposals_for_lineage(proposals),
        decisions=[],
        assist_stats=assist_stats,
    )
    s.add(ms)
    s.commit()

    draft = sess.build_draft(
        normalized,
        template_row.name,
        template_row.version,
        profile_ref,
        required_fields(template_row),
        proposals,
        rankings=(assist_stats or {}).get("rankings"),
    )
    draft_path = blobstore.drafts_dir() / f"session_{ms.id}.transform.yaml"
    draft_path.write_text(draft, encoding="utf-8")

    starter_paths: dict[str, Path] = {}
    for name, entries in sess.starter_value_maps(proposals).items():
        starter = blobstore.drafts_dir() / f"session_{ms.id}.valuemap.{name}.yaml"
        starter.write_text(
            yaml.safe_dump({"entries": entries}, sort_keys=True), encoding="utf-8"
        )
        starter_paths[name] = starter

    return StartResult(
        session_id=ms.id, mode=ms.mode, draft_path=draft_path,
        starter_paths=starter_paths, assist_stats=assist_stats,
    )


_SESSION_TO_MODE = {"manual": "none", "stub": "local", "local": "local",
                    "external": "external"}


def load_session_state(s: Session, session_id: int):
    """Session row + draft path + exemplar document row (moved from cli.py)."""
    ms = s.get(MappingSession, session_id)
    if ms is None:
        raise LookupError(f"no mapping session {session_id}")
    draft_path = blobstore.drafts_dir() / f"session_{session_id}.transform.yaml"
    doc_row = s.get(SourceDocument, ms.exemplar_document_id)
    return ms, draft_path, doc_row


def regenerate_session(
    s: Session,
    session_id: int,
    *,
    assist: str | None = None,
    client: str | None = None,
    notify: Callable[[str], None] = _noop,
) -> StartResult:
    """The full `rmu map regenerate` body (FR-016). Prior generation moves to
    assist_stats.superseded[]; refused on approved sessions."""
    ms, draft_path, doc_row = load_session_state(s, session_id)
    if ms.status == "approved":
        raise StartRefused(
            "refused: session already approved; regeneration would diverge "
            "from the approved transform (FR-016)", 3)

    template_row = get_template_by_id(s, ms.target_template_id)
    profile_row = s.get(SourceProfile, ms.source_profile_id)
    normalized = json.loads(blobstore.get_bytes(doc_row.extraction_ref))

    try:
        cfg = load_ai_config(store_root())
        mode = resolve_mode(assist, None, cfg) if assist else _SESSION_TO_MODE.get(
            ms.mode, "local"
        )
    except AiConfigError as err:
        raise StartRefused(f"error: {err}", 1) from err

    stub = ms.mode == "stub" and not assist
    session_mode = ("manual" if mode == "none" else ("stub" if stub else mode))
    client = client or (ms.assist_stats or {}).get("client")
    if mode == "external" and (not client or not has_consent(cfg, client)):
        raise StartRefused(
            f"refused: no external-API consent recorded for client {client!r} "
            f"(FR-004)", 4)

    provider = get_provider(mode, stub=stub, client=client, config=cfg)
    proposals, new_stats = generate_assist(
        mode, session_mode, stub_ai=stub, provider=provider, normalized=normalized,
        template_row=template_row, defect_codes=load_defect_codes(), client=client,
        notify=notify,
    )

    # Move the prior generation into superseded history (audit, FR-016).
    prior_stats = {k: v for k, v in (ms.assist_stats or {}).items() if k != "superseded"}
    superseded = list((ms.assist_stats or {}).get("superseded", []))
    superseded.append({"proposals": ms.proposals, "stats": prior_stats})
    if new_stats is None:
        new_stats = {"mode": session_mode, "superseded": superseded}
    else:
        new_stats["superseded"] = superseded

    ms.proposals = sess.proposals_for_lineage(proposals)
    ms.assist_stats = new_stats
    s.commit()

    draft = sess.build_draft(
        normalized, template_row.name, template_row.version,
        f"{profile_row.key}@{profile_row.structural_version}",
        required_fields(template_row), proposals,
        rankings=(new_stats or {}).get("rankings"),
    )
    draft_path.write_text(draft, encoding="utf-8")
    starter_paths: dict[str, Path] = {}
    for name, entries in sess.starter_value_maps(proposals).items():
        starter = blobstore.drafts_dir() / f"session_{session_id}.valuemap.{name}.yaml"
        starter.write_text(
            yaml.safe_dump({"entries": entries}, sort_keys=True), encoding="utf-8"
        )
        starter_paths[name] = starter

    return StartResult(
        session_id=session_id, mode=session_mode, draft_path=draft_path,
        starter_paths=starter_paths, assist_stats=new_stats,
        shown=len(proposals),
    )


def abandon_session(s: Session, session_id: int) -> None:
    """draft → abandoned; terminal states refuse (FR-039 parity both surfaces)."""
    ms = s.get(MappingSession, session_id)
    if ms is None:
        raise LookupError(f"no mapping session {session_id}")
    if ms.status != "draft":
        raise StartRefused(
            f"refused: session {session_id} is {ms.status} (terminal)", 3)
    ms.status = "abandoned"
    s.commit()
