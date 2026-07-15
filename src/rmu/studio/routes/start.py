"""Initiation routes (US5, FR-036/FR-037) — thin delegates.

An uploaded exemplar is written to a temp file and passed to the SAME
start_session / draft_*_proposal functions the CLI calls; content-addressing
makes the stored artifacts identical to a path-based CLI start (FR-036). Every
CLI rejection (drift block, unsupported-PDF ladder, kind-misuse, consent) is
surfaced with the same message.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Form, Request, UploadFile
from sqlalchemy import select

from rmu.mapping.start import StartRefused, regenerate_session, start_session
from rmu.models import SourceProfile, TargetTemplate
from rmu.onboard.drafting import (
    KindMisuse,
    OnboardRejected,
    draft_profile_proposal,
    draft_template_proposal,
)
from rmu.studio.app import DomainRefusal
from rmu.studio.routes.common import db_session, render

router = APIRouter()


def _save_upload(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "upload.pdf").suffix or ".pdf"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(upload.file.read())
    tmp.close()
    return Path(tmp.name)


@router.get("/start/session")
def start_session_form(request: Request, profile: str = "", template: str = ""):
    with db_session() as s:
        profiles = [f"{p.key}@{p.structural_version}" for p in
                    s.scalars(select(SourceProfile).order_by(SourceProfile.key))]
        templates = [f"{t.name}@{t.version}" for t in
                     s.scalars(select(TargetTemplate).order_by(TargetTemplate.name))]
    return render(request, "start.html", nav="sessions", mode="session",
                  profiles=profiles, templates=templates,
                  prefill_profile=profile, prefill_template=template)


@router.get("/start/onboarding")
def start_onboarding_form(request: Request):
    with db_session() as s:
        profiles = [f"{p.key}@{p.structural_version}" for p in
                    s.scalars(select(SourceProfile).order_by(SourceProfile.key))]
    return render(request, "start.html", nav="proposals", mode="onboarding",
                  profiles=profiles, templates=[], prefill_profile="",
                  prefill_template="")


@router.post("/start/session")
def start_session_action(request: Request, exemplar: UploadFile,
                         profile: str = Form(...), template: str = Form(...),
                         assist: str = Form(None), client: str = Form(None)):
    path = _save_upload(exemplar)
    try:
        with db_session() as s:
            try:
                result = start_session(
                    s, profile, template, path,
                    assist=(assist or None), client=(client or None),
                    no_ai=(assist == "none"),
                )
            except LookupError as err:
                raise DomainRefusal("unknown registry artifact", [str(err)]) from err
            except StartRefused as err:
                raise DomainRefusal("session start refused", [err.message]) from err
            session_id = result.session_id
            mode = result.mode
    finally:
        path.unlink(missing_ok=True)
    return render(request, "fragments/started.html", session_id=session_id,
                  mode=mode)


@router.post("/sessions/{session_id}/regenerate")
def regenerate(request: Request, session_id: int,
               assist: str = Form(None), client: str = Form(None)):
    with db_session() as s:
        try:
            regenerate_session(s, session_id, assist=(assist or None),
                               client=(client or None))
        except LookupError as err:
            raise DomainRefusal("unknown session", [str(err)]) from err
        except StartRefused as err:
            raise DomainRefusal("regenerate refused", [err.message]) from err
    from rmu.studio.geometry import session_geometry

    with db_session() as s:
        geo = session_geometry(s, session_id)
    return render(request, "fragments/started.html", session_id=session_id,
                  mode=geo["status"])


@router.post("/start/onboarding")
def start_onboarding_action(request: Request, document: UploadFile,
                            kind: str = Form(...), seed_from: str = Form(""),
                            force: bool = Form(False)):
    path = _save_upload(document)
    try:
        with db_session() as s:
            try:
                if kind == "profile":
                    outcome = draft_profile_proposal(
                        s, [path], no_ai=True, seed_from=seed_from, force=force)
                else:
                    outcome = draft_template_proposal(s, path, no_ai=True, force=force)
            except OnboardRejected as err:
                raise DomainRefusal(
                    "unsupported PDF",
                    [f"rejected: {err.rejection}", f"workaround: {err.workaround}"],
                ) from err
            except KindMisuse as err:
                # offer an explicit proceed-anyway (equivalent to --force)
                response = render(request, "fragments/kind_misuse.html",
                                  kind=kind, warning=err.warning,
                                  filename=document.filename)
                response.status_code = 422
                return response
            except LookupError as err:
                raise DomainRefusal("seed profile unknown", [str(err)]) from err
            proposal_id = outcome.proposal_id
    finally:
        path.unlink(missing_ok=True)
    return render(request, "fragments/drafted.html", proposal_id=proposal_id,
                  kind=kind)
