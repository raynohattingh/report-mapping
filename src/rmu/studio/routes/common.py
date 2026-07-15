"""Shared helpers for studio route handlers — plumbing only, no domain logic."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from rmu.db import make_engine, make_session_factory


def db_session() -> Session:
    """Fresh session against the configured DB (same resolution as the CLI)."""
    return make_session_factory(make_engine())()


def render(request: Request, name: str, /, **context):
    return request.app.state.render(name, **context)


def lease(request: Request):
    return request.app.state.lease
