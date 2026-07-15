"""Dashboard, runs and abandon actions (US6, FR-038/FR-039)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response

from rmu.mapping.start import StartRefused, abandon_session
from rmu.studio.app import DomainRefusal
from rmu.studio.dashboarddata import overview, run_detail
from rmu.studio.routes.common import db_session, render

router = APIRouter()


@router.get("/dashboard")
def dashboard(request: Request):
    with db_session() as s:
        data = overview(s)
    return render(request, "dashboard.html", nav="dashboard", **data)


@router.get("/runs/{run_id}")
def run_view(request: Request, run_id: int):
    with db_session() as s:
        detail = run_detail(s, run_id)
    if detail is None:
        return Response(status_code=404)
    return render(request, "run.html", nav="runs", run=detail)


@router.post("/sessions/{session_id}/abandon")
def abandon_session_route(request: Request, session_id: int):
    with db_session() as s:
        try:
            abandon_session(s, session_id)
        except LookupError as err:
            raise DomainRefusal("unknown session", [str(err)]) from err
        except StartRefused as err:
            raise DomainRefusal("abandon refused", [err.message]) from err
    return render(request, "fragments/abandoned.html", kind="session", id=session_id)
