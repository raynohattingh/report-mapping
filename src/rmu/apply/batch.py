"""Batch apply (FR-011, FR-016, FR-017): deterministic, non-interactive,
per-document quarantine, audit record written ONLY on completion.

No AI, no network (guarded by tests/invariants/test_no_ai_in_apply.py).
Prompt answers arrive upfront and are recorded for exact regeneration.
One run may apply SEVERAL transforms (e.g. report pack + defect CSV per
source report, FR-014 / convergence T051) under a single audit record.
"""

from __future__ import annotations

import datetime
import hashlib
import importlib
from dataclasses import dataclass, field
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
    TargetTemplate,
    Transform,
)
from rmu.registry import (
    get_profile,
    get_template,
    get_template_by_id,
    load_value_maps,
    required_fields,
    template_meta,
)
from rmu.render.csv import render_csv
from rmu.render.exceptions import exceptions_rows, write_exceptions_report
from rmu.seed import profile_config
from rmu.validate.rules import load_vocabularies, validate_rows
from rmu.validate.safecard import (
    build_safecard,
    document_verdict,
    tier_coverage,
    write_safecard,
)


class BatchError(RuntimeError):
    """Pre-run validation failure (exit 1): missing prompts, empty batch, ..."""


class DraftArtifactError(BatchError):
    """FR-016 / SC-006 (D5): an ApplyRun may only reference human-approved
    registry artifacts; a draft onboarding proposal can never convert data."""


def _raise_if_draft_artifact(session: Session, kind: str, ref: str) -> None:
    """Turn an unresolved ref into a clear draft-artifact error when draft
    onboarding proposals of that kind exist (pre-flight - no record read yet)."""
    from rmu.models import OnboardingProposal

    draft_ids = session.scalars(
        select(OnboardingProposal.id).where(
            OnboardingProposal.kind == kind,
            OnboardingProposal.status == "draft",
        )
    ).all()
    if draft_ids:
        ids = ", ".join(f"#{i}" for i in draft_ids)
        raise DraftArtifactError(
            f"{kind} {ref!r} is not a registered artifact - onboarding proposal(s) "
            f"{ids} exist with status=draft [draft_artifact]. Only human-approved "
            f"v1+ artifacts can be referenced by an ApplyRun (D5); finish review "
            f"and run 'rmu onboard approve' first."
        )


@dataclass
class _Bundle:
    """Everything one (transform, template) pair needs at apply time."""

    transform: Transform
    template_row: TargetTemplate
    doc: dict
    meta: dict
    template_bytes: bytes
    value_maps: dict
    vocabularies: dict
    tiers: float
    ref: str = field(default="")


def _bundle(session: Session, transform: Transform, template_row: TargetTemplate) -> _Bundle:
    doc = parse_transform(transform.yaml_body)
    meta = template_meta(template_row)
    if meta["kind"] not in ("csv", "docx", "pdf_form", "pdf_overlay"):
        raise BatchError(f"renderer for template kind {meta['kind']!r} not available")
    return _Bundle(
        transform=transform,
        template_row=template_row,
        doc=doc,
        meta=meta,
        template_bytes=(
            store.get_bytes(template_row.template_files[meta["file"]])
            if meta["kind"] == "docx"
            else b""
        ),
        value_maps=load_value_maps(session, doc),
        vocabularies=load_vocabularies(template_row.validation_rules or {}),
        tiers=tier_coverage(doc, required_fields(template_row)),
        ref=f"{template_row.name}@{template_row.version}",
    )


def _resolve_ref(session: Session, transform_ref: str) -> tuple[Transform, object, TargetTemplate]:
    try:
        profile_ref, template_ref = transform_ref.split(":", 1)
    except ValueError as err:
        raise BatchError(
            f"transform ref must be '<profile>@<ver>:<template>@<ver>', got {transform_ref!r}"
        ) from err
    try:
        profile_row = get_profile(session, profile_ref)
    except LookupError:
        _raise_if_draft_artifact(session, "profile", profile_ref)
        raise
    try:
        template_row = get_template(session, template_ref)
    except LookupError:
        _raise_if_draft_artifact(session, "template", template_ref)
        raise
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


def _load_bundles(
    session: Session,
    transform_refs: list[str],
    transforms_override: list[Transform] | None,
) -> tuple[list[_Bundle], object]:
    bundles: list[_Bundle] = []
    profile_row = None
    if transforms_override is not None:
        for transform in transforms_override:
            row_profile = session.get(SourceProfile, transform.source_profile_id)
            template_row = get_template_by_id(session, transform.target_template_id)
            bundles.append(_bundle(session, transform, template_row))
            profile_row = profile_row or row_profile
            if row_profile.id != profile_row.id:
                raise BatchError("all transforms in one run must share a source profile")
    else:
        for ref in transform_refs:
            transform, row_profile, template_row = _resolve_ref(session, ref)
            bundles.append(_bundle(session, transform, template_row))
            profile_row = profile_row or row_profile
            if row_profile.id != profile_row.id:
                raise BatchError("all transforms in one run must share a source profile")
    if not bundles:
        raise BatchError("at least one --transform is required")
    return bundles, profile_row


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


def _render_pack_document(
    doc: dict,
    normalized: dict,
    answers: dict,
    value_maps: dict,
    template_row,
    template_bytes: bytes,
    vocabularies: dict | None = None,
) -> tuple[bytes, list[dict], int]:
    """Report-scope rendering: header fields once + one findings row each.

    Required header fields resolve strictly (failures -> document-level
    exceptions); optional ones fall back to empty, never guessed values.
    """
    from rmu.apply.engine import resolve_record
    from rmu.render.docx import render_pack

    schema = template_row.required_schema
    header_ctx = {"header": normalized["header"], "finding": {}, "prompt": answers}
    values, problems = resolve_record(
        list(schema.get("required", [])), doc, header_ctx, value_maps, strict=True
    )
    exceptions = [
        {
            "record_ref": None,
            "kind": p["kind"],
            "detail": {"field": p["field"], "value": "", "reason": p["reason"],
                       "suggestion": p["suggestion"]},
        }
        for p in problems
    ]
    optional_values, _ = resolve_record(
        list(schema.get("optional", [])), doc, header_ctx, value_maps, strict=False
    )
    for fname, value in optional_values.items():
        values[fname] = "" if value.startswith("<<unresolved") else value

    finding_rows, finding_excs = apply_records(
        doc, normalized, answers, value_maps, list(schema.get("finding_fields", []))
    )
    exceptions.extend(finding_excs)
    # Validate stage (design §4): vocabulary-illegal rows reported, never shipped.
    finding_rows, rule_problems = validate_rows(finding_rows, vocabularies or {})
    exceptions.extend(rule_problems)
    context = {**values, "findings": finding_rows}
    return render_pack(template_bytes, context), exceptions, len(finding_rows)


def _render_pdf_documents(
    bundle: _Bundle, normalized: dict, answers: dict, stem: str
) -> tuple[list[tuple[str, bytes]], list[dict], int]:
    """Feature 003 (FR-011/FR-012/FR-013/FR-014): resolve records, render one
    filled PDF per record (or one per batch, per the template's declared
    cardinality), round-trip verify EVERY output. Verification failures and
    render problems are exceptions; the affected file never ships."""
    import tempfile

    from rmu.render.pdf_form import render_form_pdf
    from rmu.render.pdf_overlay import render_overlay_pdf
    from rmu.render.pdf_roundtrip import verify

    config = bundle.meta
    targets = sorted(
        {f["target_field"] for f in config.get("fields", [])}
        | {r["target_field"] for r in config.get("regions", [])}
    )
    rows, exceptions = apply_records(
        bundle.doc, normalized, answers, bundle.value_maps, targets
    )
    rows, rule_problems = validate_rows(rows, bundle.vocabularies)
    exceptions.extend(rule_problems)

    render = render_form_pdf if config["kind"] == "pdf_form" else render_overlay_pdf
    per_batch = config.get("cardinality") == "per_batch"
    selected = rows[:1] if per_batch else rows

    outputs: list[tuple[str, bytes]] = []
    rendered = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i, row in enumerate(selected, start=1):
            ref = row.get("finding_id") or f"record-{i}"
            suffix = "" if per_batch else f".{i:04d}"
            out_name = f"{stem}.{bundle.template_row.name}{suffix}.pdf"
            out_path = Path(tmp) / out_name
            problems = render(config, row, out_path)
            if problems:
                exceptions.extend({
                    "record_ref": ref,
                    "kind": "invalid_value",
                    "detail": {"field": p.field, "value": str(row.get(p.field, "")),
                               "reason": p.reason,
                               "suggestion": "fix the mapping/value or revise the "
                                             "template as a new version (FR-014)"},
                } for p in problems)
                continue
            report = verify(config, out_path, row)  # FR-013: every render
            if not report.ok:
                exceptions.append({
                    "record_ref": ref,
                    "kind": "render_roundtrip",
                    "detail": {"field": report.mismatches[0]["field"],
                               "value": report.mismatches[0]["got"],
                               "reason": f"round-trip mismatch: {report.mismatches}",
                               "suggestion": "rendering failure - the output was "
                                             "withheld; inspect the template regions"},
                })
                continue
            outputs.append((out_name, out_path.read_bytes()))
            rendered += 1
    return outputs, exceptions, rendered


def run_batch(
    session: Session,
    folder: Path,
    transform_refs: list[str],
    answers: dict[str, str],
    label: str = "",
    out_dir: Path | None = None,
    record_run: bool = True,
    transforms_override: list[Transform] | None = None,
) -> dict:
    """Convert every recognized, healthy PDF in `folder`; quarantine the rest.

    Returns a summary dict. The ApplyRun row is inserted only after every
    output is written (interrupted runs leave no audit record, analysis C4).
    Regeneration (FR-018) passes transforms_override (the EXACT recorded rows,
    never 'latest') with record_run=False and an explicit out_dir.
    """
    bundles, profile_row = _load_bundles(session, transform_refs, transforms_override)

    all_prompt_keys: set[str] = set()
    for b in bundles:
        all_prompt_keys.update(prompt_keys(b.doc))
    missing = sorted(all_prompt_keys - set(answers))
    if missing:
        raise BatchError(
            "missing per-batch prompt answers (supply --answer key=value): "
            + ", ".join(missing)
        )

    pdfs = sorted(Path(folder).glob("*.pdf"))
    if not pdfs:
        raise BatchError(f"empty batch: no PDF documents in {folder}")

    worst_tiers = min(b.tiers for b in bundles)
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
                           "reason": "duplicate of an earlier document in this batch",
                           "suggestion": "remove the duplicate file; it was converted once"},
            }]
            per_doc_exceptions.append((name, exc))
            verdicts.append(document_verdict(
                document=name, sha256=sha, blocked_reason="duplicate in batch",
                blocked_kind="duplicate", rows_converted=0, findings_total=0,
                exceptions=exc, tiers=worst_tiers))
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
                           "suggestion": f"onboard this shape: rmu onboard draft-profile "
                                         f"{name} (FR-021)"},
            }]
            per_doc_exceptions.append((name, exc))
            _get_or_create_document(session, sha, name, None)
            verdicts.append(document_verdict(
                document=name, sha256=sha,
                blocked_reason="unrecognized source shape", blocked_kind="unknown_profile",
                rows_converted=0, findings_total=0, exceptions=exc, tiers=worst_tiers))
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
                           "suggestion": f"structure drifted: rmu onboard draft-profile "
                                         f"{name} --seed-from {matched.key}@"
                                         f"{matched.structural_version} - review the delta, "
                                         f"approve a new profile version (FR-021)"},
            }]
            per_doc_exceptions.append((name, exc))
            _get_or_create_document(session, sha, name, matched.id)
            verdicts.append(document_verdict(
                document=name, sha256=sha, blocked_reason=reason,
                blocked_kind="drift_block", rows_converted=0,
                findings_total=len(normalized["findings"]), exceptions=exc,
                tiers=worst_tiers))
            continue

        _get_or_create_document(session, sha, name, matched.id)
        doc_exceptions: list[dict] = []
        rows_total = 0
        for b in bundles:
            if b.meta["kind"] == "csv":
                rows, exceptions = apply_records(
                    b.doc, normalized, answers, b.value_maps, b.meta["columns"]
                )
                rows, rule_problems = validate_rows(rows, b.vocabularies)
                exceptions.extend(rule_problems)
                content = render_csv(rows, b.meta["columns"])
                out_name, out_kind = f"{pdf.stem}.defects.csv", "defect_csv"
                n_rows = len(rows)
            elif b.meta["kind"] in ("pdf_form", "pdf_overlay"):
                # feature 003 (D7/D10): filled PDFs w/ mandatory round-trip
                pdf_outputs, exceptions, n_rows = _render_pdf_documents(
                    b, normalized, answers, pdf.stem
                )
                for e in exceptions:
                    e["template"] = b.ref
                for out_name, content in pdf_outputs:
                    outputs.append((out_name, content))
                    manifest.append({
                        "document_sha": sha,
                        "output_kind": b.meta["kind"],
                        "template": b.ref,
                        "filename": out_name,
                        "store_hash": store.put_bytes(content),
                    })
                doc_exceptions.extend(exceptions)
                rows_total += n_rows
                continue
            else:  # docx report pack (record_scope: report)
                content, exceptions, n_rows = _render_pack_document(
                    b.doc, normalized, answers, b.value_maps, b.template_row,
                    b.template_bytes, b.vocabularies,
                )
                out_name, out_kind = f"{pdf.stem}.pack.docx", "annexc_pack"
            for e in exceptions:
                e["template"] = b.ref
            outputs.append((out_name, content))
            manifest.append({
                "document_sha": sha,
                "output_kind": out_kind,
                "template": b.ref,
                "filename": out_name,
                "store_hash": store.put_bytes(content),
            })
            doc_exceptions.extend(exceptions)
            rows_total += n_rows
        per_doc_exceptions.append((name, doc_exceptions))
        verdicts.append(document_verdict(
            document=name, sha256=sha, blocked_reason=None, blocked_kind=None,
            rows_converted=rows_total, findings_total=len(normalized["findings"]),
            exceptions=doc_exceptions, tiers=worst_tiers))

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
            transform_id=bundles[0].transform.id,
            transform_ids=[b.transform.id for b in bundles],
            target_template_id=bundles[0].template_row.id,
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
