"""Engine/session factories + append-only enforcement (Constitution III, research R2).

Model-layer enforcement is portable across SQLite/Postgres: a before_flush
listener rejects UPDATE/DELETE on the ★ registries. New versions are new rows.
"""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from rmu.config import db_url
from rmu.models import APPEND_ONLY_MODELS


class AppendOnlyViolation(RuntimeError):
    """Raised on any UPDATE/DELETE against an append-only registry table."""


@event.listens_for(Session, "before_flush")
def _reject_mutation(session: Session, flush_context, instances) -> None:
    for obj in session.dirty:
        if isinstance(obj, APPEND_ONLY_MODELS) and session.is_modified(
            obj, include_collections=False
        ):
            raise AppendOnlyViolation(
                f"UPDATE on append-only table {type(obj).__name__}: create a new version instead"
            )
    for obj in session.deleted:
        if isinstance(obj, APPEND_ONLY_MODELS):
            raise AppendOnlyViolation(
                f"DELETE on append-only table {type(obj).__name__}: rows are never removed"
            )


def make_engine(url: str | None = None) -> Engine:
    engine = create_engine(url or db_url())
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _record):  # R9: enforce FKs on SQLite
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
