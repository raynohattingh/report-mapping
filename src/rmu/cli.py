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
app.add_typer(db_app, name="db")
app.add_typer(seed_app, name="seed")
app.add_typer(profile_app, name="profile")
app.add_typer(template_app, name="template")
app.add_typer(valuemap_app, name="valuemap")


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


if __name__ == "__main__":
    app()
