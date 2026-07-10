"""Batch apply (FR-011, FR-016, FR-017): deterministic, non-interactive,
per-document quarantine, audit record written ONLY on completion.

No AI, no network (guarded by tests/invariants/test_no_ai_in_apply.py).
Prompt answers arrive upfront and are recorded for exact regeneration.
"""

from __future__ import annotations

import datetime
import hashlib
import importlib
import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rmu import store
from rmu.apply.records import apply_records
from rmu.mapping.loader import parse_transform, prompt_keys
from rmu.models import (
    ApplyRun,
    ConversionException,
    SourceDocument,
    SourceProfile,
    Transform,
)
from rmu.registry import (
    get_profile,
    get_template,
    load_value_maps,
    required_fields,
    template_meta,
)
from rmu.render.csv import render_csv
from rmu.render.exceptions import exceptions_rows, write_exceptions_report
from rmu.seed import profile_config
from rmu.validate.safecard import (
    build_safecard,
    document_verdict,
    tier_coverage,
    write_safecard,
)


class BatchError(RuntimeError):
    """Pre-run validation failure (exit 1): missing prompts, empty batch, ..."""


def _get_transform(session: Session, transform_ref: str) -> tuple[Transform, object, object]:
    try:
        profile_ref, template_ref = transform_ref.split(":", 1)
    except ValueError as err:
        raise BatchError(
            f"transform ref must be '<profile>@<ver>:<template>@<ver>', got {transform_ref!r}"
        ) from err
    profile_row = get_profile(session, profile_ref)
    template_row = get_template(session, template_ref)
    version = session.scalar(
        select(func.max(Transform.version)).where(
            Transform.source_profile_id == profile_row.id,
            Transform.target_template_id == template_row.id,
        )
    )
    if version is None:
        raise BatchError(f"no approved transform for {transform_ref} (run a mapping session)")
    transform = session.scalar(
        select(Transform).where(
            Transform.source_profile_id == profile_row.id,
            Transform.target_template_id == template_row.id,
            Transform.version == version,
        )
    )
    return transform, profile_row, template_row


def _get_or_create_document(session: Session, sha: str, filename: str, profile_id) -> None:
    row = session.scalar(select(SourceDocument).where(SourceDocument.sha256 == sha))
    if row is None:
        session.add(
            SourceDocument(
                sha256=sha,
                original_filename=filename,
                profile_id=profile_id,
                received_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.flush()


def run_batch(
    session: Session,
    folder: Path,
    transform_ref: str,
    answers: dict[str, str],
    label: str = "",
    out_dir: Path | None = None,
    record_run: bool = True,
) -> dict:
    """Convert every recognized, healthy PDF in `folder`; quarantine the rest.

    Returns a summary dict. The ApplyRun row is inserted only after every
    output is written (interrupted runs leave no audit record, analysis C4).
    Set out_dir/record_run for regeneration replays (FR-018).
    """
    transform, profile_row, template_row = _get_transform(session, transform_ref)
    doc = parse_transform(transform.yaml_body)

    missing = sorted(set(prompt_keys(doc)) - set(answers))
    if missing:
        raise BatchError(
            "missing per-batch prompt answers (supply --answer key=value): "
            + ", ".join(missing)
        )

    pdfs = sorted(Path(folder).glob("*.pdf"))
    if not pdfs:
        raise BatchError(f"empty batch: no PDF documents in {folder}")

    value_maps = load_value_maps(session, doc)
    meta = template_meta(template_row)
    if meta["kind"] != "csv":
        raise BatchError(f"renderer for template kind {meta['kind']!r} not available")
    columns = meta["columns"]
    required = required_fields(template_row)
    tiers = tier_coverage(doc, required)
    profiles = list(session.scalars(select(SourceProfile)))
    extractor_cache: dict[int, tuple[object, dict]] = {}

    document_shas: list[str] = []
    manifest: list[dict] = []
    per_doc_exceptions: list[tuple[str, list[dict]]] = []
    verdicts: list[dict] = []
    seen: set[str] = set()

    digest = hashlib.sha256()
    outputs: list[tuple[str, bytes]] = []  # (filename, content) written at the end

    from rmu.detect import detect_profile

    for pdf in pdfs:
        data = pdf.read_bytes()
        sha = store.sha256_bytes(data)
        digest.update(sha.encode())
        name = pdf.name

        if sha in seen:
            exc = [{
                "record_ref": None,
                "kind": "duplicate",
                "detail": {"field": "", "value": sha[:12],
                           "reason": f"duplicate of an earlier document in this batch",
                           "suggestion": "remove the duplicate file; it was converted once"},
            }]
            per_doc_exceptions.append((name, exc))
            verdicts.append(document_verdict(
                document=name, sha256=sha, blocked_reason="duplicate in batch",
                blocked_kind="duplicate", rows_converted=0, findings_total=0,
                exceptions=exc, tiers=tiers))
            continue
        seen.add(sha)
        document_shas.append(sha)
        store.put_bytes(data)  # inputs retrievable by fingerprint for regen

        matched = detect_profile(pdf, profiles)
        if matched is None or matched.id != profile_row.id:
            exc = [{
                "record_ref": None,
                "kind": "unknown_profile",
                "detail": {"field": "", "value": "",
                           "reason": "document does not match any known source profile",
                           "suggestion": "route to a mapping session as a possible new "
                                         "profile version"},
            }]
            per_doc_exceptions.append((name, exc))
            _get_or_create_document(session, sha, name, None)
            verdicts.append(document_verdict(
                document=name, sha256=sha,
                blocked_reason="unrecognized source shape", blocked_kind="unknown_profile",
                rows_converted=0, findings_total=0, exceptions=exc, tiers=tiers))
            continue

        if matched.id not in extractor_cache:
            extractor_cache[matched.id] = (
                importlib.import_module(matched.extractor_ref),
                profile_config(f"{matched.key}@{matched.structural_version}"),
            )
        extractor, cfg = extractor_cache[matched.id]
        normalized = extractor.extract(pdf, cfg)
        blocked, reason = extractor.is_blocked(normalized)
        if blocked:
            exc = [{
                "record_ref": None,
                "kind": "drift_block",
                "detail": {"field": "", "value": "",
                           "reason": reason,
                           "suggestion": "human review: suspected new profile version; "
                                         "re-map once and register it"},
            }]
            per_doc_exceptions.append((name, exc))
            _get_or_create_document(session, sha, name, matched.id)
            verdicts.append(document_verdict(
                document=name, sha256=sha, blocked_reason=reason,
                blocked_kind="drift_block", rows_converted=0,
                findings_total=len(normalized["findings"]), exceptions=exc, tiers=tiers))
            continue

        _get_or_create_document(session, sha, name, matched.id)
        rows, exceptions = apply_records(doc, normalized, answers, value_maps, columns)
        content = render_csv(rows, columns)
        out_name = f"{pdf.stem}.defects.csv"
        outputs.append((out_name, content))
        manifest.append({
            "document_sha": sha,
            "output_kind": "defect_csv",
            "filename": out_name,
            "store_hash": store.put_bytes(content),
        })
        per_doc_exceptions.append((name, exceptions))
        verdicts.append(document_verdict(
            document=name, sha256=sha, blocked_reason=None, blocked_kind=None,
            rows_converted=len(rows), findings_total=len(normalized["findings"]),
            exceptions=exceptions, tiers=tiers))

    run_dir = out_dir or store.runs_dir(f"pending-{digest.hexdigest()[:12]}")
    for out_name, content in outputs:
        (run_dir / out_name).write_bytes(content)

    exc_rows = exceptions_rows(per_doc_exceptions)
    exceptions_path = write_exceptions_report(run_dir, exc_rows)
    exceptions_ref = store.put_file(exceptions_path)

    safecard = build_safecard(verdicts)
    write_safecard(run_dir, safecard)

    run_id = None
    if record_run:
        run = ApplyRun(
            batch_label=label or Path(folder).name,
            document_shas=document_shas,
            prompt_answers=answers,
            transform_id=transform.id,
            target_template_id=template_row.id,
            safecard=safecard,
            outputs_manifest=manifest,
            exceptions_report_ref=exceptions_ref,
            completed_at=datetime.datetime.now(datetime.UTC),  # completion-only write
        )
        session.add(run)
        session.flush()
        for doc_name, excs in per_doc_exceptions:
            doc_sha = next((v["sha256"] for v in verdicts if v["document"] == doc_name), "")
            for e in excs:
                session.add(ConversionException(
                    apply_run_id=run.id,
                    document_sha=doc_sha,
                    record_ref=e.get("record_ref"),
                    kind=e["kind"],
                    detail=e["detail"],
                ))
        session.commit()
        run_id = run.id
        final_dir = store.runs_dir(str(run_id))
        if run_dir != final_dir:
            for item in run_dir.iterdir():
                item.rename(final_dir / item.name)
            run_dir.rmdir()
            run_dir = final_dir

    converted = sum(1 for v in verdicts if v["verdict"] != "block")
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "documents": len(verdicts),
        "converted": converted,
        "blocked": len(verdicts) - converted,
        "exceptions": len(exc_rows),
        "manifest": manifest,
    }
