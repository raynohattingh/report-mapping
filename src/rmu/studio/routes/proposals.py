"""Visual onboarding review routes (US4, FR-032..FR-035a) — thin delegates.

Element edits go through Proposal.set_review_state/add_element/bulk_confirm_page
(the shared write path — same review_state/corrected_payload a YAML hand-edit
writes); approval runs onboard.approve verify-on-approve, showing the persisted
per-check report on failure and offering — never auto-starting — the next step
on success.
"""

from __future__ import annotations

import yaml
from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

from rmu.onboard.approve import VerifyFailure, approve_profile, approve_template
from rmu.onboard.proposal import Proposal, ProposalStateError, UnresolvedElementsError
from rmu.studio.app import DomainRefusal
from rmu.studio.geometry import proposal_geometry
from rmu.studio.routes.common import db_session, render

router = APIRouter()


def _parse_yaml(text: str, what: str) -> dict:
    """Parse an analyst-supplied element payload → a clean 422 on a typo."""
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as err:
        raise DomainRefusal(f"invalid {what}", [f"not valid YAML: {err}"]) from err
    if not isinstance(parsed, dict):
        raise DomainRefusal(f"invalid {what}", ["payload must be a mapping"])
    return parsed


def _load(s, proposal_id: int) -> Proposal:
    try:
        return Proposal.load(s, proposal_id)
    except ProposalStateError as err:
        raise DomainRefusal("unknown proposal", [str(err)]) from err


def _require_draft(p: Proposal) -> None:
    if p.status != "draft":
        raise DomainRefusal(
            "proposal is read-only",
            [f"cannot edit: proposal #{p.id} is {p.status} (terminal)"],
        )


@router.get("/proposals/{proposal_id}")
def proposal_view(request: Request, proposal_id: int):
    with db_session() as s:
        geo = proposal_geometry(s, proposal_id)
    return render(request, "proposal.html", nav="proposals", geo=geo,
                  proposal_id=proposal_id, read_only=geo["status"] != "draft")


@router.get("/proposals/{proposal_id}/geometry")
def proposal_geometry_json(request: Request, proposal_id: int):
    with db_session() as s:
        geo = proposal_geometry(s, proposal_id)
    response = JSONResponse(geo)
    response.headers["cache-control"] = "no-store"
    return response


def _update_fragment(request: Request, proposal_id: int):
    with db_session() as s:
        geo = proposal_geometry(s, proposal_id)
    return render(request, "fragments/triage_update.html", proposal_id=proposal_id,
                  geo=geo, read_only=geo["status"] != "draft")


@router.post("/proposals/{proposal_id}/elements/{element_id}")
def edit_element(request: Request, proposal_id: int, element_id: str,
                 action: str = Form(...), payload: str = Form("")):
    with db_session() as s:
        p = _load(s, proposal_id)
        _require_draft(p)
        try:
            if action == "confirm":
                p.set_review_state(element_id, "confirmed")
            elif action == "remove":
                p.set_review_state(element_id, "removed")
            elif action == "correct":
                p.set_review_state(element_id, "corrected",
                                   corrected_payload=_parse_yaml(payload,
                                                                 "corrected payload"))
            else:
                raise DomainRefusal("edit refused", [f"unknown action '{action}'"])
        except ProposalStateError as err:
            raise DomainRefusal("edit refused", [str(err)]) from err
    return _update_fragment(request, proposal_id)


@router.post("/proposals/{proposal_id}/elements")
def add_element(request: Request, proposal_id: int,
                element_kind: str = Form(...), payload: str = Form(...)):
    with db_session() as s:
        p = _load(s, proposal_id)
        _require_draft(p)
        try:
            p.add_element({"element_kind": element_kind,
                           "payload": _parse_yaml(payload, "element payload")})
        except (ProposalStateError, KeyError) as err:
            raise DomainRefusal("add refused", [str(err)]) from err
    return _update_fragment(request, proposal_id)


@router.post("/proposals/{proposal_id}/bulk-confirm")
def bulk_confirm(request: Request, proposal_id: int, page: int = Form(...)):
    with db_session() as s:
        p = _load(s, proposal_id)
        _require_draft(p)
        p.bulk_confirm_page(page)
    return _update_fragment(request, proposal_id)


@router.post("/proposals/{proposal_id}/abandon")
def abandon(request: Request, proposal_id: int):
    with db_session() as s:
        p = _load(s, proposal_id)
        try:
            p.mark_abandoned()
        except ProposalStateError as err:
            raise DomainRefusal("abandon refused", [str(err)]) from err
    return _update_fragment(request, proposal_id)


@router.post("/proposals/{proposal_id}/approve")
def approve(request: Request, proposal_id: int,
            name: str = Form(""), as_ref: str = Form(""), by: str = Form("")):
    """Verify-on-approve then register (FR-035); on failure show the per-check
    report; on success offer the next step (FR-035a)."""
    operator = by or "studio"
    with db_session() as s:
        p = _load(s, proposal_id)
        try:
            p.ensure_approvable()
        except UnresolvedElementsError as err:
            raise DomainRefusal("approval blocked", [str(err)]) from err
        except ProposalStateError as err:
            raise DomainRefusal("approval refused", [str(err)]) from err

        try:
            if p.kind == "profile":
                if "@" not in as_ref:
                    raise DomainRefusal("approval needs identity",
                                        ["profile approval needs key@version"])
                key, _, version = as_ref.partition("@")
                row = approve_profile(s, p, key, version, operator)
                registered = f"SourceProfile {row.key}@{row.structural_version}"
                next_kind = "profile"
                next_ref = f"{row.key}@{row.structural_version}"
            else:
                if "@" not in name:
                    raise DomainRefusal("approval needs identity",
                                        ["template approval needs name@version"])
                tname, _, tver = name.partition("@")
                row = approve_template(s, p, tname, int(tver), operator)
                registered = f"TargetTemplate {row.name}@{row.version}"
                next_kind = "template"
                next_ref = f"{row.name}@{row.version}"
        except VerifyFailure as err:
            with db_session() as s2:
                geo = proposal_geometry(s2, proposal_id)
            response = render(request, "fragments/verify_report.html",
                              proposal_id=proposal_id, report=err.report, geo=geo)
            response.status_code = 422
            return response
        except ProposalStateError as err:
            raise DomainRefusal("approval refused", [str(err)]) from err

    return render(request, "fragments/registered.html", proposal_id=proposal_id,
                  registered=registered, by=operator,
                  next_kind=next_kind, next_ref=next_ref)
