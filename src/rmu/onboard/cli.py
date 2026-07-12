"""`rmu onboard` sub-app (feature 003, contracts/cli-onboard.md).

Exit codes: 0 success, 1 user-actionable rejection (with diagnosis), 2 internal
error / not-yet-available. All commands are local-only (FR-020). Analysis and
approval cores land in T013+/T018+; the kind ladder, misuse warnings, and the
proposal lifecycle are live from this scaffold.
"""

from __future__ import annotations

from pathlib import Path

import typer

onboard_app = typer.Typer(no_args_is_help=True, add_completion=False)


def _session_factory():
    from rmu.db import make_engine, make_session_factory

    return make_session_factory(make_engine())


def _reject(diag) -> None:
    typer.echo(f"rejected: {diag.rejection}")
    typer.echo(f"workaround: {diag.workaround}")
    raise typer.Exit(1)


def _check_misuse(pdf: Path, command: str, force: bool) -> None:
    from rmu.onboard.pdf_kind import misuse_warning

    warning = misuse_warning(pdf, command=command)
    if warning and not force:
        typer.echo(f"warning: {warning}")
        raise typer.Exit(1)


@onboard_app.command("draft-profile")
def draft_profile(
    exemplars: list[str] = typer.Argument(..., help="exemplar PDF(s) of the new source shape"),
    no_ai: bool = typer.Option(False, "--no-ai", help="heuristics-only proposal (FR-020)"),
    seed_from: str = typer.Option("", "--seed-from",
                                  help="existing profile key@version to seed a drift "
                                       "re-onboarding proposal (FR-021)"),
    force: bool = typer.Option(False, "--force",
                               help="proceed despite a document-kind warning (FR-023)"),
) -> None:
    """Analyse an unrecognised source PDF into a draft profile proposal."""
    from rmu.onboard.pdf_kind import diagnose

    paths = [Path(p) for p in exemplars]
    for p in paths:
        if not p.exists():
            typer.echo(f"error: no such file {p}")
            raise typer.Exit(1)
    diag = diagnose(paths[0])
    if diag.kind is None:
        _reject(diag)
    _check_misuse(paths[0], "draft-profile", force)
    typer.echo("error: source analysis not yet available (T013)")  # scaffold boundary
    raise typer.Exit(2)


@onboard_app.command("draft-template")
def draft_template(
    target: str = typer.Argument(..., help="target-format PDF"),
    no_ai: bool = typer.Option(False, "--no-ai"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Analyse a target-format PDF into a draft template proposal."""
    from rmu.onboard.pdf_kind import diagnose

    pdf = Path(target)
    if not pdf.exists():
        typer.echo(f"error: no such file {pdf}")
        raise typer.Exit(1)
    diag = diagnose(pdf)
    if diag.kind is None:
        _reject(diag)
    _check_misuse(pdf, "draft-template", force)
    typer.echo("error: target analysis not yet available (T024)")  # scaffold boundary
    raise typer.Exit(2)


@onboard_app.command("review")
def review(
    proposal_id: int = typer.Argument(...),
    regenerate_sheet: bool = typer.Option(False, "--regenerate-sheet"),
) -> None:
    """Show proposal status: element review states and what blocks approval."""
    from rmu.onboard.proposal import Proposal, ProposalStateError

    with _session_factory()() as s:
        try:
            p = Proposal.load(s, proposal_id)
        except ProposalStateError as err:
            typer.echo(f"error: {err}")
            raise typer.Exit(1) from err
        typer.echo(f"proposal #{p.id}  kind={p.kind}  status={p.status}")
        typer.echo(f"draft: {p.draft_path()}")
        states: dict[str, int] = {}
        for e in p.elements:
            states[e["review_state"]] = states.get(e["review_state"], 0) + 1
        typer.echo("elements: " + ", ".join(f"{k}={v}" for k, v in sorted(states.items())))
        for e in p.elements:
            flags = f"  flags={','.join(e['flags'])}" if e.get("flags") else ""
            typer.echo(f"  [{e['review_state']:9}] {e['id']} "
                       f"({e['element_kind']}, conf={e['confidence']:.2f}){flags}")
        pending = p.unresolved()
        if pending:
            typer.echo(f"blocks approval: {', '.join(pending)} still 'proposed'")
        elif p.status == "draft":
            typer.echo("ready to approve")
        if p.row.verify_report and not p.row.verify_report.get("ok", True):
            typer.echo(f"last verify failure: {p.row.verify_report}")
        if p.status == "approved":
            typer.echo(
                f"approved by {p.row.approved_by} at {p.row.approved_at} "
                f"-> profile_id={p.row.resulting_profile_id} "
                f"template_id={p.row.resulting_template_id}"
            )
        if regenerate_sheet:
            typer.echo("error: review sheet not yet available (T016)")
            raise typer.Exit(2)


@onboard_app.command("approve")
def approve(
    proposal_id: int = typer.Argument(...),
    as_ref: str = typer.Option("", "--as", help="profile key@version, e.g. zeitview.pdf.roof@v1"),
    name: str = typer.Option("", "--name", help="template name@version, e.g. ias.defect_form@1"),
    by: str = typer.Option("", "--by", help="approver identity (FR-017)"),
) -> None:
    """Verify-on-approve then register (FR-022): approval is a machine-checked proof."""
    from rmu.onboard.proposal import Proposal, ProposalStateError

    with _session_factory()() as s:
        try:
            p = Proposal.load(s, proposal_id)
            p.ensure_approvable()
        except ProposalStateError as err:
            typer.echo(f"error: {err}")
            raise typer.Exit(1) from err
        typer.echo("error: verify-on-approve not yet available (T018/T026)")
        raise typer.Exit(2)


@onboard_app.command("abandon")
def abandon(proposal_id: int = typer.Argument(...)) -> None:
    """Mark a draft abandoned. Abandoned drafts affect nothing, ever."""
    from rmu.onboard.proposal import Proposal, ProposalStateError

    with _session_factory()() as s:
        try:
            p = Proposal.load(s, proposal_id, sync=False)
            p.mark_abandoned()
        except ProposalStateError as err:
            typer.echo(f"error: {err}")
            raise typer.Exit(1) from err
        typer.echo(f"proposal #{proposal_id}: abandoned")
