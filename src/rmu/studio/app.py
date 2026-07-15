"""Studio app factory (feature 004, D6/D11) — routes per contracts/http-routes.md.

Zero business logic lives here or in any handler: routes delegate to the same
functions the CLI calls and render the result (FR-001). The error contract is
centralized: 403 auth (middleware), 409 draft conflict, 422 domain refusal with
the CLI's message verbatim, 503 database-busy as a retryable fragment.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from rmu.studio.auth import COOKIE_NAME, LaunchContext, StudioAuthMiddleware

_PKG = Path(__file__).parent


class DomainRefusal(Exception):
    """A refusal from an existing code path; `reasons` are shown verbatim."""

    def __init__(self, title: str, reasons: list[str]):
        self.title = title
        self.reasons = reasons
        super().__init__(f"{title}: {'; '.join(reasons)}")


def make_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(_PKG / "templates"),
        autoescape=select_autoescape(["html"]),
    )
    return env


def create_app(ctx: LaunchContext) -> FastAPI:
    from rmu.studio.concurrency import DraftLease

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ctx = ctx
    app.state.templates = make_env()
    app.state.lease = DraftLease()
    app.add_middleware(StudioAuthMiddleware, ctx=ctx)
    app.mount("/static", StaticFiles(directory=_PKG / "static"), name="static")

    def render(name: str, /, **context) -> HTMLResponse:
        template = app.state.templates.get_template(name)
        response = HTMLResponse(template.render(studio_token=ctx.token, **context))
        response.headers["cache-control"] = "no-store"  # FR-043
        return response

    app.state.render = render

    @app.get("/", include_in_schema=False)
    def key_exchange(request: Request) -> RedirectResponse:
        # The middleware already validated the key; move the secret out of the
        # URL and into an HttpOnly cookie (FR-040a).
        response = RedirectResponse("/dashboard", status_code=303)
        response.set_cookie(
            COOKIE_NAME, ctx.token, httponly=True, samesite="strict",
            path="/",
        )
        return response

    @app.exception_handler(DomainRefusal)
    def domain_refusal(request: Request, exc: DomainRefusal):
        response = render("fragments/refusal.html", title=exc.title,
                          reasons=exc.reasons)
        response.status_code = 422
        return response

    from sqlalchemy.exc import OperationalError

    @app.exception_handler(OperationalError)
    def database_busy(request: Request, exc: OperationalError):
        # A CLI batch/migration holds SQLite: retryable, nothing partially
        # applied (edge case "Database busy").
        response = render("fragments/busy.html", detail=str(exc.orig))
        response.status_code = 503
        response.headers["retry-after"] = "2"
        return response

    from rmu.mapping.loader import TransformValidationError

    @app.exception_handler(TransformValidationError)
    def invalid_draft(request: Request, exc: TransformValidationError):
        # A draft hand-corrupted to invalid YAML/schema (e.g. via the editor)
        # must surface as a clean refusal even on a GET, never a 500.
        response = render("fragments/refusal.html",
                          title="draft is not schema-valid", reasons=exc.errors)
        response.status_code = 422
        return response

    from rmu.studio.concurrency import DraftConflict

    @app.exception_handler(DraftConflict)
    def draft_conflict(request: Request, exc: DraftConflict):
        response = render(
            "fragments/conflict.html", path=exc.path.name, diff=exc.diff,
            base_hash=exc.base_hash, current_hash=exc.current_hash,
            base_known=exc.base_known,
        )
        response.status_code = 409
        return response

    from rmu.studio.routes import (
        ai as ai_routes,
    )
    from rmu.studio.routes import (
        dashboard as dashboard_routes,
    )
    from rmu.studio.routes import (
        documents as document_routes,
    )
    from rmu.studio.routes import (
        links as link_routes,
    )
    from rmu.studio.routes import (
        preview as preview_routes,
    )
    from rmu.studio.routes import (
        proposals as proposal_routes,
    )
    from rmu.studio.routes import (
        sessions as session_routes,
    )
    from rmu.studio.routes import (
        start as start_routes,
    )

    for module in (dashboard_routes, document_routes, session_routes, link_routes,
                   preview_routes, proposal_routes, start_routes, ai_routes):
        app.include_router(module.router)

    return app
