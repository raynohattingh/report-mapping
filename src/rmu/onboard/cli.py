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
    from rmu.onboard.drafting import KindMisuse, OnboardRejected, draft_profile_proposal

    with _session_factory()() as s:
        try:
            outcome = draft_profile_proposal(
                s, [Path(p) for p in exemplars],
                no_ai=no_ai, seed_from=seed_from, force=force,
            )
        except FileNotFoundError as err:
            typer.echo(str(err))
            raise typer.Exit(1) from err
        except OnboardRejected as err:
            typer.echo(f"rejected: {err.rejection}")
            typer.echo(f"workaround: {err.workaround}")
            raise typer.Exit(1) from err
        except KindMisuse as err:
            typer.echo(f"warning: {err.warning}")
            raise typer.Exit(1) from err
        except LookupError as err:
            typer.echo(f"error: {err}")
            raise typer.Exit(1) from err

    document = outcome.document
    low = sum(1 for e in document["elements"] if e["confidence"] < 0.5)
    flagged = sum(1 for e in document["elements"] if e.get("flags"))
    typer.echo(f"proposal: {outcome.proposal_id}")
    typer.echo(f"draft: {outcome.draft_path}")
    typer.echo(f"review sheet: {outcome.sheet_path}")
    typer.echo(
        f"elements: {len(document['elements'])} "
        f"(low-confidence: {low}, flagged: {flagged})"
    )
    if document.get("ai_assist"):
        typer.echo(
            f"ai hints: {len(document['ai_assist']['enrichments'])} "
            f"(local, pages {document['ai_assist']['sampled_pages']})"
        )
    if document.get("diagnosis"):
        typer.echo(f"diagnosis: {document['diagnosis']['notes']}")
    typer.echo(
        "next: review each element against the PDF, edit the draft YAML, "
        "then 'rmu onboard approve'"
    )


@onboard_app.command("draft-template")
def draft_template(
    target: str = typer.Argument(..., help="target-format PDF"),
    no_ai: bool = typer.Option(False, "--no-ai"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Analyse a target-format PDF into a draft template proposal."""
    from rmu.onboard.drafting import KindMisuse, OnboardRejected, draft_template_proposal

    with _session_factory()() as s:
        try:
            outcome = draft_template_proposal(s, Path(target), no_ai=no_ai, force=force)
        except FileNotFoundError as err:
            typer.echo(str(err))
            raise typer.Exit(1) from err
        except OnboardRejected as err:
            typer.echo(f"rejected: {err.rejection}")
            typer.echo(f"workaround: {err.workaround}")
            raise typer.Exit(1) from err
        except KindMisuse as err:
            typer.echo(f"warning: {err.warning}")
            raise typer.Exit(1) from err

    document = outcome.document
    flagged = sum(1 for e in document["elements"] if e.get("flags"))
    typer.echo(f"proposal: {outcome.proposal_id}")
    typer.echo(f"kind: {'pdf_form' if outcome.pdf_kind == 'form' else 'pdf_overlay'}")
    typer.echo(f"draft: {outcome.draft_path}")
    typer.echo(f"review sheet: {outcome.sheet_path}")
    typer.echo(f"elements: {len(document['elements'])} (flagged: {flagged})")
    typer.echo(
        "next: review fields/regions + cardinality, edit the draft YAML, "
        "then 'rmu onboard approve --name <name>@<version>'"
    )


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
            from rmu.onboard.review_sheet import write_sheet

            typer.echo(f"review sheet: {write_sheet(p.document, p.id)}")


@onboard_app.command("approve")
def approve(
    proposal_id: int = typer.Argument(...),
    as_ref: str = typer.Option("", "--as", help="profile key@version, e.g. acme.pdf.roof@v1"),
    name: str = typer.Option("", "--name", help="template name@version, e.g. ias.defect_form@1"),
    by: str = typer.Option("", "--by", help="approver identity (FR-017)"),
) -> None:
    """Verify-on-approve then register (FR-022): approval is a machine-checked proof."""
    import getpass

    from rmu.onboard.approve import VerifyFailure, approve_profile
    from rmu.onboard.proposal import Proposal, ProposalStateError

    operator = by or getpass.getuser()  # FR-017: who approved
    with _session_factory()() as s:
        try:
            p = Proposal.load(s, proposal_id)
        except ProposalStateError as err:
            typer.echo(f"error: {err}")
            raise typer.Exit(1) from err

        if p.kind == "profile":
            if not as_ref or "@" not in as_ref:
                typer.echo("error: profile approval needs --as <key>@<version>")
                raise typer.Exit(1)
            key, _, version = as_ref.partition("@")
            try:
                row = approve_profile(s, p, key, version, operator)
            except VerifyFailure as err:
                typer.echo(f"error: {err}")
                typer.echo("proposal stays draft; verify report persisted "
                           "(rmu onboard review to inspect)")
                raise typer.Exit(1) from err
            except ProposalStateError as err:
                typer.echo(f"error: {err}")
                raise typer.Exit(1) from err
            typer.echo(
                f"registered: SourceProfile {row.key}@{row.structural_version} "
                f"(id {row.id}), approved by {operator}"
            )
            typer.echo("this shape now detects and extracts deterministically - no AI")
        else:
            from rmu.onboard.approve import approve_template

            if not name or "@" not in name:
                typer.echo("error: template approval needs --name <name>@<version>")
                raise typer.Exit(1)
            tname, _, tver = name.partition("@")
            try:
                row = approve_template(s, p, tname, int(tver), operator)
            except VerifyFailure as err:
                typer.echo(f"error: {err}")
                typer.echo("proposal stays draft; verify report persisted")
                raise typer.Exit(1) from err
            except ProposalStateError as err:
                typer.echo(f"error: {err}")
                raise typer.Exit(1) from err
            typer.echo(
                f"registered: TargetTemplate {row.name}@{row.version} "
                f"(id {row.id}), approved by {operator}"
            )


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
