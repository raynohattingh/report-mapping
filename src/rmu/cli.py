"""`rmu` CLI (Typer) — contracts/cli-commands.md.

Exit codes: 0 success, 1 usage/validation error, 2 blocked, 3 approval
preconditions unmet.
"""

from __future__ import annotations

import typer
from sqlalchemy import select

from rmu.db import make_engine, make_session_factory
from rmu.models import SourceProfile, TargetTemplate, ValueMap

app = typer.Typer(no_args_is_help=True, add_completion=False)
db_app = typer.Typer(no_args_is_help=True)
seed_app = typer.Typer(no_args_is_help=True)
profile_app = typer.Typer(no_args_is_help=True)
template_app = typer.Typer(no_args_is_help=True)
valuemap_app = typer.Typer(no_args_is_help=True)
map_app = typer.Typer(no_args_is_help=True)
apply_app = typer.Typer(no_args_is_help=True)
runs_app = typer.Typer(no_args_is_help=True)
app.add_typer(db_app, name="db")
app.add_typer(seed_app, name="seed")
app.add_typer(profile_app, name="profile")
app.add_typer(template_app, name="template")
app.add_typer(valuemap_app, name="valuemap")
app.add_typer(map_app, name="map")
app.add_typer(apply_app, name="apply")
app.add_typer(runs_app, name="runs")


def session_factory():
    return make_session_factory(make_engine())


@db_app.command("init")
def db_init() -> None:
    """Create/upgrade the schema via Alembic (idempotent)."""
    from alembic import command
    from alembic.config import Config

    from rmu.config import REPO_ROOT

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    command.upgrade(cfg, "head")
    typer.echo("db: schema at head")


@seed_app.command("load")
def seed_load() -> None:
    """Load profiles, interim templates, defect vocabulary (idempotent)."""
    from rmu.seed import seed_all

    with session_factory()() as s:
        result = seed_all(s)
    typer.echo(
        f"seed: profiles+{len(result['profiles'])} templates+{len(result['templates'])} "
        f"defect_codes={result['defect_codes']}"
    )


@profile_app.command("list")
def profile_list() -> None:
    with session_factory()() as s:
        for p in s.scalars(select(SourceProfile).order_by(SourceProfile.key)):
            typer.echo(
                f"{p.key}@{p.structural_version}  status={p.status}  "
                f"effective={p.effective_from}"
            )


@template_app.command("list")
def template_list() -> None:
    with session_factory()() as s:
        for t in s.scalars(
            select(TargetTemplate).order_by(TargetTemplate.name, TargetTemplate.version)
        ):
            flag = "INTERIM" if t.interim else "REAL"
            typer.echo(f"{t.name}@{t.version}  [{flag}]  effective={t.effective_from}")


@valuemap_app.command("list")
def valuemap_list() -> None:
    with session_factory()() as s:
        for v in s.scalars(select(ValueMap).order_by(ValueMap.name, ValueMap.version)):
            typer.echo(f"{v.name}@{v.version}  entries={len(v.entries)}")


@valuemap_app.command("create")
def valuemap_create(
    name: str = typer.Option(...),
    file: str = typer.Option(
        ..., help="YAML file: {entries: [{source_value, target_value, provenance, note?}]}"
    ),
) -> None:
    """Insert a NEW version of a named value map (append-only, FR-019)."""
    import datetime

    import yaml

    from rmu.registry import next_value_map_version

    entries = yaml.safe_load(open(file, encoding="utf-8"))["entries"]
    for e in entries:
        if e.get("provenance") not in ("human", "ai-accepted"):
            typer.echo(f"error: entry {e.get('source_value')!r} needs provenance human|ai-accepted")
            raise typer.Exit(1)
    with session_factory()() as s:
        version = next_value_map_version(s, name)
        s.add(ValueMap(name=name, version=version, entries=entries,
                       effective_from=datetime.date.today()))
        s.commit()
    typer.echo(f"valuemap: created {name}@{version} ({len(entries)} entries)")


def _load_session_state(s, session_id: int):
    from rmu import store as blobstore
    from rmu.models import MappingSession, SourceDocument

    ms = s.get(MappingSession, session_id)
    if ms is None:
        typer.echo(f"error: no mapping session {session_id}")
        raise typer.Exit(1)
    draft_path = blobstore.drafts_dir() / f"session_{session_id}.transform.yaml"
    doc_row = s.get(SourceDocument, ms.exemplar_document_id)
    return ms, draft_path, doc_row


@map_app.command("start")
def map_start(
    profile: str = typer.Option(..., help="e.g. scopito.pdf.powerline@v2020"),
    template: str = typer.Option(..., help="e.g. interim.defect_csv@1"),
    exemplar: str = typer.Option(..., help="path to ONE exemplar source report"),
    no_ai: bool = typer.Option(False, "--no-ai", help="pure-manual session (A6/D3 core path)"),
    stub_ai: bool = typer.Option(False, "--stub-ai", hidden=True, help="test-only canned provider"),
) -> None:
    """Start a HIL mapping session against one exemplar (US1, design §6)."""
    import datetime
    import importlib
    import json
    from pathlib import Path

    import yaml

    from rmu import store as blobstore
    from rmu.detect import detect_profile
    from rmu.mapping import session as sess
    from rmu.mapping.providers import get_provider
    from rmu.models import MappingSession, SourceDocument, SourceProfile
    from rmu.registry import get_profile, get_template, required_fields
    from rmu.seed import load_defect_codes, profile_config

    exemplar_path = Path(exemplar)
    with session_factory()() as s:
        profile_row = get_profile(s, profile)
        template_row = get_template(s, template)

        detected = detect_profile(exemplar_path, list(s.scalars(select(SourceProfile))))
        if detected is None or detected.id != profile_row.id:
            typer.echo("blocked: exemplar does not match the requested profile fingerprint")
            raise typer.Exit(2)

        cfg = profile_config(profile)
        extractor = importlib.import_module(profile_row.extractor_ref)
        normalized = extractor.extract(exemplar_path, cfg)
        blocked, reason = extractor.is_blocked(normalized)
        if blocked:
            typer.echo(f"blocked: exemplar failed integrity: {reason}")
            raise typer.Exit(2)

        extraction_ref = blobstore.put_bytes(
            json.dumps(normalized, sort_keys=True).encode("utf-8")
        )
        doc_row = SourceDocument(
            sha256=normalized["source_sha256"],
            original_filename=exemplar_path.name,
            profile_id=profile_row.id,
            received_at=datetime.datetime.now(datetime.UTC),
            extraction_ref=extraction_ref,
        )
        s.add(doc_row)
        s.flush()

        provider = get_provider(no_ai=no_ai, stub=stub_ai)
        proposals = provider.propose(
            normalized, required_fields(template_row), load_defect_codes()
        )
        ms = MappingSession(
            source_profile_id=profile_row.id,
            target_template_id=template_row.id,
            exemplar_document_id=doc_row.id,
            mode="manual" if no_ai else "ai",
            proposals=sess.proposals_for_lineage(proposals),
            decisions=[],
        )
        s.add(ms)
        s.commit()

        draft = sess.build_draft(
            normalized,
            template_row.name,
            template_row.version,
            profile,
            required_fields(template_row),
            proposals,
        )
        draft_path = blobstore.drafts_dir() / f"session_{ms.id}.transform.yaml"
        draft_path.write_text(draft, encoding="utf-8")
        typer.echo(f"session: {ms.id} mode={ms.mode}")
        typer.echo(f"draft:   {draft_path}")
        for name, entries in sess.starter_value_maps(proposals).items():
            starter = blobstore.drafts_dir() / f"session_{ms.id}.valuemap.{name}.yaml"
            starter.write_text(
                yaml.safe_dump({"entries": entries}, sort_keys=True), encoding="utf-8"
            )
            typer.echo(f"valuemap starter (review, then `rmu valuemap create --name {name} "
                       f"--file {starter}`): {starter}")


@map_app.command("preview")
def map_preview(session_id: int = typer.Option(..., "--session")) -> None:
    """Render the exemplar through the current draft for human verification (FR-008)."""
    import json

    from rmu import store as blobstore
    from rmu.apply.engine import resolve_record
    from rmu.mapping.loader import parse_transform
    from rmu.registry import get_template_by_id, load_value_maps, template_meta
    from rmu.render.csv import render_csv

    with session_factory()() as s:
        ms, draft_path, doc_row = _load_session_state(s, session_id)
        doc = parse_transform(draft_path.read_text(encoding="utf-8"))
        normalized = json.loads(blobstore.get_bytes(doc_row.extraction_ref))
        template_row = get_template_by_id(s, ms.target_template_id)
        meta = template_meta(template_row)
        vmaps = load_value_maps(s, doc)

        prompt_placeholders = {
            p["key"]: f"<<{p['key']}>>" for p in doc.get("prompts", [])
        }
        columns = meta.get("columns") or list(template_row.required_schema["required"])
        rows = []
        problems_total = 0
        for finding in normalized["findings"]:
            context = {"header": normalized["header"], "finding": finding,
                       "prompt": prompt_placeholders}
            values, problems = resolve_record(columns, doc, context, vmaps, strict=False)
            problems_total += len(problems)
            rows.append(values)
        out = blobstore.drafts_dir() / f"session_{session_id}.preview.csv"
        out.write_bytes(render_csv(rows, columns))
        typer.echo(f"preview: {out}  (rows={len(rows)}, unresolved cells={problems_total})")


@map_app.command("review")
def map_review(session_id: int = typer.Option(..., "--session")) -> None:
    """Regenerate the HTML review sheet from the current draft (FR-006)."""
    import json

    from rmu import store as blobstore
    from rmu.mapping.loader import TransformValidationError, parse_transform
    from rmu.mapping.review_sheet import build_review_html
    from rmu.models import SourceProfile
    from rmu.registry import get_template_by_id, required_fields

    with session_factory()() as s:
        ms, draft_path, doc_row = _load_session_state(s, session_id)
        try:
            doc = parse_transform(draft_path.read_text(encoding="utf-8"))
        except TransformValidationError as err:
            typer.echo("error: draft is not schema-valid; fix before review:")
            for e in err.errors:
                typer.echo(f"  - {e}")
            raise typer.Exit(1) from err
        normalized = json.loads(blobstore.get_bytes(doc_row.extraction_ref))
        template_row = get_template_by_id(s, ms.target_template_id)
        profile_row = s.get(SourceProfile, ms.source_profile_id)
        html = build_review_html(
            session_id,
            ms.mode,
            f"{profile_row.key}@{profile_row.structural_version}",
            f"{template_row.name}@{template_row.version}",
            doc_row.original_filename,
            doc,
            normalized,
            required_fields(template_row),
        )
        out = blobstore.drafts_dir() / f"session_{session_id}.review.html"
        out.write_text(html, encoding="utf-8")
        typer.echo(f"review sheet: {out}")


@map_app.command("approve")
def map_approve(
    session_id: int = typer.Option(..., "--session"),
    by: str = typer.Option(..., help="approver identity (FR-009)"),
) -> None:
    """Validate preconditions and store the Transform (versioned, append-only)."""
    import datetime

    from sqlalchemy import func

    from rmu.mapping.approve import ApprovalRefused, check_approval
    from rmu.mapping.loader import TransformValidationError, parse_transform
    from rmu.mapping.session import compute_decisions
    from rmu.models import Transform
    from rmu.registry import get_template_by_id, required_fields

    with session_factory()() as s:
        ms, draft_path, _doc_row = _load_session_state(s, session_id)
        template_row = get_template_by_id(s, ms.target_template_id)
        text = draft_path.read_text(encoding="utf-8")
        try:
            doc = parse_transform(text)
            check_approval(doc, required_fields(template_row), s)
        except TransformValidationError as err:
            typer.echo("refused: draft is not schema-valid:")
            for e in err.errors:
                typer.echo(f"  - {e}")
            raise typer.Exit(3) from err
        except ApprovalRefused as err:
            typer.echo("refused: approval preconditions unmet (FR-007):")
            for r in err.reasons:
                typer.echo(f"  - {r}")
            raise typer.Exit(3) from err

        current = s.scalar(
            select(func.max(Transform.version)).where(
                Transform.source_profile_id == ms.source_profile_id,
                Transform.target_template_id == ms.target_template_id,
            )
        )
        version = (current or 0) + 1
        transform = Transform(
            source_profile_id=ms.source_profile_id,
            target_template_id=ms.target_template_id,
            version=version,
            effective_from=datetime.date.today(),
            yaml_body=text,
            approved_by=by,
            approved_at=datetime.datetime.now(datetime.UTC),
            parent_version=current,
        )
        s.add(transform)
        s.flush()
        ms.decisions = compute_decisions(ms.proposals, doc)
        ms.status = "approved"
        ms.resulting_transform_id = transform.id
        s.commit()
        typer.echo(f"approved: transform v{version} (id={transform.id}) by {by}; "
                   f"{len(ms.decisions)} decisions recorded")


def _parse_answers(answers: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in answers:
        key, sep, value = item.partition("=")
        if not sep:
            typer.echo(f"error: --answer must be key=value, got {item!r}")
            raise typer.Exit(1)
        parsed[key] = value
    return parsed


@apply_app.command("run")
def apply_run(
    folder: str = typer.Argument(..., help="folder of same-shape source PDFs"),
    transform: str = typer.Option(
        ..., help="e.g. scopito.pdf.powerline@v2020:interim.defect_csv@1"
    ),
    answer: list[str] = typer.Option([], "--answer", help="per-batch prompt answer key=value"),
    label: str = typer.Option("", help="batch label for the audit record"),
) -> None:
    """Deterministic zero-decision batch conversion (US2). Never interactive."""
    from pathlib import Path

    from rmu.apply.batch import BatchError, run_batch

    with session_factory()() as s:
        try:
            summary = run_batch(s, Path(folder), transform, _parse_answers(answer), label)
        except (BatchError, LookupError) as err:
            typer.echo(f"error: {err}")
            raise typer.Exit(1) from err
    typer.echo(
        f"run {summary['run_id']}: documents={summary['documents']} "
        f"converted={summary['converted']} blocked={summary['blocked']} "
        f"exceptions={summary['exceptions']}"
    )
    typer.echo(f"outputs: {summary['run_dir']}")
    if summary["converted"] == 0:
        typer.echo("blocked: no document in this batch could be converted")
        raise typer.Exit(2)


@runs_app.command("list")
def runs_list() -> None:
    from rmu.models import ApplyRun

    with session_factory()() as s:
        for r in s.scalars(select(ApplyRun).order_by(ApplyRun.id)):
            b = r.safecard["batch"]
            typer.echo(
                f"run {r.id}  label={r.batch_label}  docs={b['total']} "
                f"verdicts={b['verdicts']}  transform_id={r.transform_id}"
            )


@runs_app.command("show")
def runs_show(run_id: int = typer.Argument(...)) -> None:
    import json

    from rmu.models import ApplyRun

    with session_factory()() as s:
        r = s.get(ApplyRun, run_id)
        if r is None:
            typer.echo(f"error: no run {run_id}")
            raise typer.Exit(1)
        typer.echo(json.dumps({
            "id": r.id,
            "label": r.batch_label,
            "document_shas": r.document_shas,
            "prompt_answers": r.prompt_answers,
            "transform_id": r.transform_id,
            "target_template_id": r.target_template_id,
            "safecard_batch": r.safecard["batch"],
            "outputs_manifest": r.outputs_manifest,
            "exceptions_report_ref": r.exceptions_report_ref,
        }, indent=1, sort_keys=True))


if __name__ == "__main__":
    app()
