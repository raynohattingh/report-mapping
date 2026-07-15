"""Mapping-canvas routes (US1, FR-010..FR-019) — thin delegates.

Draft mutations run through rmu.studio.draftedit (split/validate/render under
the DraftLease); refusals surface the existing messages verbatim (FR-001).
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

from rmu.mapping.loader import TransformValidationError, parse_transform
from rmu.mapping.start import load_session_state
from rmu.studio import draftedit
from rmu.studio.app import DomainRefusal
from rmu.studio.geometry import link_projection, session_geometry
from rmu.studio.routes.common import db_session, lease, render

router = APIRouter()


def _load(s, session_id: int):
    try:
        return load_session_state(s, session_id)
    except LookupError as err:
        raise DomainRefusal("unknown session", [str(err)]) from err


def _require_draft(ms) -> None:
    if ms.status != "draft":
        raise DomainRefusal(
            "session is read-only",
            [f"refused: session {ms.id} is {ms.status} (terminal)"],
        )


def _mutate(request: Request, session_id: int, base_hash: str,
            overwrite: bool, mutate) -> None:
    with db_session() as s:
        ms, draft_path, _ = _load(s, session_id)
        _require_draft(ms)
        try:
            draftedit.apply_doc_edit(
                lease(request), draft_path, base_hash, mutate,
                overwrite=overwrite,
            )
        except draftedit.RouteEditError as err:
            raise DomainRefusal("edit refused", [str(err)]) from err
        except TransformValidationError as err:
            raise DomainRefusal("draft is not schema-valid", err.errors) from err


def _draft_hash(request: Request, session_id: int) -> str:
    with db_session() as s:
        _, draft_path, _ = _load(s, session_id)
    _, digest = lease(request).load(draft_path)
    return digest


def _canvas_update(request: Request, session_id: int, state: str = ""):
    with db_session() as s:
        geo = session_geometry(s, session_id)
    links = geo["links"]
    if state:
        links = [link for link in links if link["state"] == state]
    return render(request, "fragments/canvas_update.html",
                  session_id=session_id, links=links, gate=geo["gate"],
                  state=state, read_only=geo["status"] != "draft",
                  draft_hash=_draft_hash(request, session_id))


@router.get("/sessions/{session_id}")
def session_view(request: Request, session_id: int):
    with db_session() as s:
        geo = session_geometry(s, session_id)
        _, draft_path, _ = _load(s, session_id)
    _, draft_hash = lease(request).load(draft_path)
    return render(request, "session.html", nav="sessions", geo=geo,
                  session_id=session_id, draft_hash=draft_hash,
                  read_only=geo["status"] != "draft")


@router.get("/sessions/{session_id}/geometry")
def session_geometry_json(request: Request, session_id: int):
    with db_session() as s:
        geo = session_geometry(s, session_id)
    geo["draft_hash"] = _draft_hash(request, session_id)
    response = JSONResponse(geo)
    response.headers["cache-control"] = "no-store"
    return response


@router.get("/sessions/{session_id}/fragments/links")
def links_fragment(request: Request, session_id: int, state: str = ""):
    with db_session() as s:
        ms, draft_path, _ = _load(s, session_id)
    doc = parse_transform(draft_path.read_text(encoding="utf-8"))
    links = link_projection(doc)
    if state:
        links = [link for link in links if link["state"] == state]
    return render(request, "fragments/links.html", session_id=session_id,
                  links=links, state=state, read_only=ms.status != "draft")


@router.get("/sessions/{session_id}/fragments/readiness")
def readiness_fragment(request: Request, session_id: int):
    with db_session() as s:
        geo = session_geometry(s, session_id)
    return render(request, "fragments/readiness.html", session_id=session_id,
                  gate=geo["gate"], oob=False)


@router.post("/sessions/{session_id}/routes")
def create_route(request: Request, session_id: int,
                 field: str = Form(...), source: str = Form(...),
                 base_hash: str = Form(...), overwrite: bool = Form(False)):
    _mutate(request, session_id, base_hash, overwrite,
            lambda doc: draftedit.create_route(doc, field, source))
    return _canvas_update(request, session_id)


@router.post("/sessions/{session_id}/routes/{field}")
def edit_route(request: Request, session_id: int, field: str,
               action: str = Form(...), source: str = Form(""),
               base_hash: str = Form(...), overwrite: bool = Form(False)):
    def mutate(doc: dict) -> None:
        if action == "accept":
            draftedit.accept_route(doc, field)
        elif action == "reject":
            draftedit.reject_route(doc, field)
        elif action == "reroute":
            draftedit.reroute(doc, field, source)
        elif action == "delete":
            draftedit.delete_route(doc, field)
        else:
            raise draftedit.RouteEditError(f"unknown action '{action}'")

    _mutate(request, session_id, base_hash, overwrite, mutate)
    return _canvas_update(request, session_id)


@router.get("/sessions/{session_id}/approve/dialog")
def approve_dialog(request: Request, session_id: int):
    with db_session() as s:
        ms, _, _ = _load(s, session_id)
        geo = session_geometry(s, session_id)
    return render(request, "fragments/approve_dialog.html", session_id=session_id,
                  gate=geo["gate"], read_only=ms.status != "draft")


@router.post("/sessions/{session_id}/approve")
def approve(request: Request, session_id: int, by: str = Form("")):
    """Run the same gate as `rmu map approve` and store the same Transform row."""
    from rmu.mapping.approve import ApprovalRefused, approve_session
    from rmu.mapping.loader import TransformValidationError
    from rmu.mapping.start import StartRefused

    with db_session() as s:
        try:
            transform, ms = approve_session(s, session_id, by or "studio")
        except LookupError as err:
            raise DomainRefusal("unknown session", [str(err)]) from err
        except TransformValidationError as err:
            raise DomainRefusal("draft is not schema-valid", err.errors) from err
        except ApprovalRefused as err:
            raise DomainRefusal("approval preconditions unmet (FR-007)",
                                err.reasons) from err
        except StartRefused as err:
            raise DomainRefusal("approval refused", [err.message]) from err
        version = transform.version
        transform_id = transform.id
        decisions = len(ms.decisions)
    return render(request, "fragments/approved.html", session_id=session_id,
                  version=version, transform_id=transform_id, by=by or "studio",
                  decisions=decisions)
