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
ai_app = typer.Typer(no_args_is_help=True)
ai_consent_app = typer.Typer(no_args_is_help=True)
ai_app.add_typer(ai_consent_app, name="consent")
app.add_typer(db_app, name="db")
app.add_typer(seed_app, name="seed")
app.add_typer(profile_app, name="profile")
app.add_typer(template_app, name="template")
app.add_typer(valuemap_app, name="valuemap")
app.add_typer(map_app, name="map")
app.add_typer(apply_app, name="apply")
app.add_typer(runs_app, name="runs")
app.add_typer(ai_app, name="ai")

from rmu.onboard.cli import onboard_app  # noqa: E402  (feature 003, D5)

app.add_typer(onboard_app, name="onboard")


@app.command("studio")
def studio(
    port: int = typer.Option(None, "--port", help="port on 127.0.0.1 (default: first free)"),
    no_browser: bool = typer.Option(False, "--no-browser", help="print the URL only"),
) -> None:
    """Launch the Mapping Studio — strictly-local web HIL surface (feature 004, D6).

    Binds 127.0.0.1 only; prints a per-launch secret URL (FR-040/FR-040a)."""
    try:
        from rmu.studio.launch import run_studio  # lazy: optional dep group (D11)
    except ModuleNotFoundError as err:
        typer.echo("error: studio dependencies are not installed - run "
                   "`uv sync --group studio` (optional group, D11)")
        raise typer.Exit(1) from err
    run_studio(port=port, open_browser=not no_browser)


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


@profile_app.command("suggest")
def profile_suggest(pdf: str = typer.Argument(..., help="path to a source PDF")) -> None:
    """Suggest which registered profiles a new document resembles (FR-015).

    Session-side onboarding aid only — apply-time detection is unchanged. Scores
    are 'resembles', never a match verdict (Principle V)."""
    from pathlib import Path

    from rmu.ai.config import load_ai_config
    from rmu.ai.embeddings import EmbeddingBackend
    from rmu.ai.fingerprint_similarity import suggest_profiles
    from rmu.config import store_root

    cfg = load_ai_config(store_root())
    backend = EmbeddingBackend(cfg.embedding_model)
    if not backend.available():
        typer.echo("unavailable: tier-1 embeddings not installed; run `rmu ai setup` "
                   f"({backend.reason})")
        raise typer.Exit(5)

    with session_factory()() as s:
        profiles = list(s.scalars(select(SourceProfile).order_by(SourceProfile.key)))
    suggestions = suggest_profiles(Path(pdf), profiles, backend)
    if not suggestions:
        typer.echo("no registered profiles to compare against (run `rmu seed load`?)")
        return
    for item in suggestions:
        typer.echo(f"resembles {item['profile']} ({item['score']:.2f})")


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
    import yaml

    from rmu.registry import create_value_map

    entries = yaml.safe_load(open(file, encoding="utf-8"))["entries"]
    with session_factory()() as s:
        try:
            version = create_value_map(s, name, entries)
        except ValueError as err:
            typer.echo(str(err))
            raise typer.Exit(1) from err
    typer.echo(f"valuemap: created {name}@{version} ({len(entries)} entries)")


def _load_session_state(s, session_id: int):
    """CLI wrapper over the shared loader: not-found becomes echo + exit 1."""
    from rmu.mapping.start import load_session_state

    try:
        return load_session_state(s, session_id)
    except LookupError as err:
        typer.echo(f"error: {err}")
        raise typer.Exit(1) from err


@map_app.command("start")
def map_start(
    profile: str = typer.Option(..., help="e.g. scopito.pdf.powerline@v2020"),
    template: str = typer.Option(..., help="e.g. interim.defect_csv@1"),
    exemplar: str = typer.Option(..., help="path to ONE exemplar source report"),
    assist: str = typer.Option(
        None, "--assist", help="assistance mode: none|local|external (default: config or local)"
    ),
    client: str = typer.Option(
        None, "--client", help="client id (required for --assist external, consent-gated)"
    ),
    no_ai: bool = typer.Option(False, "--no-ai", help="alias for --assist none (A6/D3 core path)"),
    stub_ai: bool = typer.Option(False, "--stub-ai", hidden=True, help="test-only canned provider"),
) -> None:
    """Start a HIL mapping session against one exemplar (US1, design §6)."""
    from pathlib import Path

    from rmu.mapping.start import StartRefused, start_session

    with session_factory()() as s:
        try:
            result = start_session(
                s, profile, template, Path(exemplar),
                assist=assist, client=client, no_ai=no_ai, stub_ai=stub_ai,
                notify=lambda m: typer.echo(m, err=True),
            )
        except StartRefused as err:
            typer.echo(err.message)
            raise typer.Exit(err.exit_code) from err

    typer.echo(f"session: {result.session_id} mode={result.mode}")
    typer.echo(f"draft:   {result.draft_path}")
    if result.assist_stats is not None:
        dropped_total = sum(result.assist_stats["dropped"].values())
        typer.echo(f"assist:  {result.assist_stats['mode']} "
                   f"shown={result.assist_stats['shown']} dropped={dropped_total}")
    for name, starter in result.starter_paths.items():
        typer.echo(f"valuemap starter (review, then `rmu valuemap create --name {name} "
                   f"--file {starter}`): {starter}")


@map_app.command("regenerate")
def map_regenerate(
    session_id: int = typer.Option(..., "--session"),
    assist: str = typer.Option(None, "--assist", help="override the session's mode"),
    client: str = typer.Option(None, "--client", help="client id (external mode)"),
) -> None:
    """Explicitly replace a session's persisted proposal set (FR-016).

    The prior generation is moved into `assist_stats.superseded[]` — nothing is
    silently changed; re-opening a session never mutates what is under review
    unless the analyst runs this. Refused on approved sessions."""
    from rmu.mapping.start import StartRefused, regenerate_session

    with session_factory()() as s:
        try:
            result = regenerate_session(
                s, session_id, assist=assist, client=client,
                notify=lambda m: typer.echo(m, err=True),
            )
        except LookupError as err:
            typer.echo(f"error: {err}")
            raise typer.Exit(1) from err
        except StartRefused as err:
            typer.echo(err.message)
            raise typer.Exit(err.exit_code) from err

    new_stats = result.assist_stats
    prior = new_stats["superseded"][-1]
    dropped_total = sum(new_stats.get("dropped", {}).values())
    typer.echo(f"regenerated session {session_id}: superseded "
               f"{len(prior['proposals'])} proposal(s) from "
               f"{prior['stats'].get('generated_at', '?')}")
    typer.echo(f"assist:  {result.mode} shown={result.shown} dropped={dropped_total}")


@map_app.command("preview")
def map_preview(session_id: int = typer.Option(..., "--session")) -> None:
    """Render the exemplar through the current draft INTO ITS TARGET FORMAT for
    human verification (FR-008) — CSV templates preview as CSV, docx templates
    as a rendered (canonicalized) pack (convergence T052), PDF templates as the
    real form-fill/overlay output (feature 004, FR-030)."""
    from rmu.mapping.preview import build_preview

    with session_factory()() as s:
        try:
            result = build_preview(s, session_id)
        except LookupError as err:
            typer.echo(f"error: {err}")
            raise typer.Exit(1) from err
    typer.echo(f"preview: {result.out_path}  (rows={len(result.rows)}, "
               f"unresolved cells={result.unresolved})")
    for problem in result.render_problems:
        typer.echo(f"render problem: {problem['field']}: {problem['reason']} "
                   f"[{problem['kind']}]")


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
            assist_stats=ms.assist_stats,
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
    from rmu.mapping.approve import ApprovalRefused, approve_session
    from rmu.mapping.loader import TransformValidationError
    from rmu.mapping.start import StartRefused

    with session_factory()() as s:
        try:
            transform, ms = approve_session(s, session_id, by)
        except LookupError as err:
            typer.echo(f"error: {err}")
            raise typer.Exit(1) from err
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
        except StartRefused as err:
            typer.echo(err.message)
            raise typer.Exit(err.exit_code) from err
        typer.echo(f"approved: transform v{transform.version} (id={transform.id}) "
                   f"by {by}; {len(ms.decisions)} decisions recorded")


@map_app.command("abandon")
def map_abandon(session_id: int = typer.Option(..., "--session")) -> None:
    """Mark a draft session abandoned (terminal). Abandoned drafts affect
    nothing, ever — same transition the studio dashboard offers (FR-039)."""
    from rmu.mapping.start import StartRefused, abandon_session

    with session_factory()() as s:
        try:
            abandon_session(s, session_id)
        except LookupError as err:
            typer.echo(f"error: {err}")
            raise typer.Exit(1) from err
        except StartRefused as err:
            typer.echo(err.message)
            raise typer.Exit(err.exit_code) from err
    typer.echo(f"session {session_id}: abandoned")


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
    transform: list[str] = typer.Option(
        ...,
        "--transform",
        help="repeatable; e.g. scopito.pdf.powerline@v2020:interim.defect_csv@1 "
             "(pass twice to produce the report pack AND the defect CSV in one run)",
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


@apply_app.command("regen")
def apply_regen(
    run_id: int = typer.Argument(...),
    out: str = typer.Option("", help="output directory (default store/regen/<run-id>)"),
) -> None:
    """Reproduce a past run EXACTLY from its audit record; hash-verify every
    output against the recorded manifest (FR-018). Never re-asks prompts."""
    import shutil
    from pathlib import Path

    from sqlalchemy import select as sa_select

    from rmu import store as blobstore
    from rmu.apply.batch import run_batch
    from rmu.config import store_root
    from rmu.models import ApplyRun, SourceDocument, Transform

    with session_factory()() as s:
        r = s.get(ApplyRun, run_id)
        if r is None:
            typer.echo(f"error: no run {run_id}")
            raise typer.Exit(1)
        transform_rows = [
            s.get(Transform, tid) for tid in (r.transform_ids or [r.transform_id])
        ]

        # Rebuild the input folder from content fingerprints (research R3).
        inputs = store_root() / "regen" / f"{run_id}-inputs"
        if inputs.exists():
            shutil.rmtree(inputs)
        inputs.mkdir(parents=True)
        for sha in r.document_shas:
            doc_row = s.scalar(
                sa_select(SourceDocument).where(SourceDocument.sha256 == sha)
            )
            name = doc_row.original_filename if doc_row else f"{sha[:12]}.pdf"
            shutil.copyfile(blobstore.get_path(sha), inputs / name)

        out_dir = Path(out) if out else store_root() / "regen" / str(run_id)
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True)

        summary = run_batch(
            s, inputs, [], r.prompt_answers,
            out_dir=out_dir, record_run=False, transforms_override=transform_rows,
        )

    expected = {m["filename"]: m["store_hash"] for m in r.outputs_manifest}
    regenerated = {m["filename"]: m["store_hash"] for m in summary["manifest"]}
    mismatched = sorted(
        set(expected) ^ set(regenerated)
        | {f for f in expected if f in regenerated and expected[f] != regenerated[f]}
    )
    if mismatched:
        typer.echo(f"REGENERATION MISMATCH for run {run_id}: {', '.join(mismatched)}")
        raise typer.Exit(1)
    typer.echo(
        f"regenerated run {run_id}: {len(expected)} outputs hash-verified "
        f"against the recorded manifest"
    )
    typer.echo(f"outputs: {out_dir}")


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


@ai_app.command("doctor")
def ai_doctor(
    json_out: bool = typer.Option(False, "--json", help="machine-readable output"),
) -> None:
    """Per-tier asset/runtime health (FR-014). Reporting only; exit 0 always."""
    import json as _json

    from rmu.ai.config import load_ai_config
    from rmu.ai.doctor import health
    from rmu.config import store_root

    report = health(load_ai_config(store_root()))
    if json_out:
        typer.echo(_json.dumps(report, indent=1, sort_keys=True))
        return
    emb = report["embedding"]
    llm = report["llm"]
    typer.echo(f"default mode      : {report['default_mode']}")
    typer.echo(f"tier 1 embeddings : {'OK' if emb['ok'] else 'MISSING'}  "
               f"({emb['model']}){'' if emb['ok'] else '  ' + str(emb['reason'])}")
    bound = "loopback" if llm["loopback_bound"] else "NON-LOOPBACK (refused)"
    typer.echo(f"tier 2 local LLM  : {'OK' if llm['ok'] else 'MISSING'}  "
               f"({llm['model']} on {llm['host']}, {bound})"
               f"{'' if llm['ok'] else '  ' + str(llm['reason'])}")
    vision = report["vision"]
    vbound = "loopback" if vision["loopback_bound"] else "NON-LOOPBACK (refused)"
    typer.echo(f"{vision['label']:18}: {'OK' if vision['ok'] else 'MISSING'}  "
               f"({vision['model']} on {vision['host']}, {vbound})"
               f"{'' if vision['ok'] else '  ' + str(vision['reason'])}")
    clients = report["consent_clients"]
    typer.echo(f"external consent  : {', '.join(clients) if clients else 'none recorded'}")


@ai_app.command("setup")
def ai_setup() -> None:
    """Print the documented manual setup steps (FR-014). Downloads nothing."""
    from rmu.ai.doctor import SETUP_STEPS

    typer.echo(SETUP_STEPS)


@ai_consent_app.command("grant")
def ai_consent_grant(
    client: str = typer.Option(..., "--client"),
    by: str = typer.Option(..., "--by", help="owner identity recording consent"),
    note: str = typer.Option(None, "--note"),
) -> None:
    """Record per-client external-API consent (FR-004). Only writer of consent."""
    from rmu.ai.config import grant_consent
    from rmu.config import store_root

    entry = grant_consent(store_root(), client, by, note)
    typer.echo(f"consent granted: {entry['client']} by {entry['granted_by']} "
               f"at {entry['granted_at']}")


@ai_consent_app.command("revoke")
def ai_consent_revoke(
    client: str = typer.Option(..., "--client"),
    by: str = typer.Option(..., "--by", help="owner identity recording the revocation"),
) -> None:
    """Remove a client's external-API consent (FR-004)."""
    from rmu.ai.config import revoke_consent
    from rmu.config import store_root

    removed = revoke_consent(store_root(), client, by)
    if removed:
        typer.echo(f"consent revoked: {client} by {by}")
    else:
        typer.echo(f"no consent entry for client {client!r}")


@ai_consent_app.command("list")
def ai_consent_list() -> None:
    from rmu.ai.config import list_consent, load_ai_config
    from rmu.config import store_root

    entries = list_consent(load_ai_config(store_root()))
    if not entries:
        typer.echo("no external-API consent recorded")
        return
    for e in entries:
        note = f"  ({e['note']})" if e.get("note") else ""
        typer.echo(f"{e['client']}  granted_by={e['granted_by']}  at={e['granted_at']}{note}")


if __name__ == "__main__":
    app()
