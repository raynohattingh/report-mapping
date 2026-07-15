"""AI health & consent (US6, FR-039/FR-044) — thin delegates.

Health is the existing `ai.doctor.health` report (never mutates state); consent
grant/revoke record exactly the fields the CLI `rmu ai consent` commands record.
The studio invokes NO AI here — it only reports and manages consent.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request

from rmu.ai.config import (
    grant_consent,
    list_consent,
    load_ai_config,
    revoke_consent,
)
from rmu.ai.doctor import health
from rmu.config import store_root
from rmu.studio.app import DomainRefusal
from rmu.studio.routes.common import render

router = APIRouter()


@router.get("/ai")
def ai_view(request: Request):
    cfg = load_ai_config(store_root())
    report = health(cfg)
    return render(request, "ai.html", nav="ai", report=report,
                  consent=list_consent(cfg))


@router.post("/ai/consent")
def ai_consent(request: Request, action: str = Form(...),
               client: str = Form(...), by: str = Form(...),
               note: str = Form("")):
    root = store_root()
    if action == "grant":
        grant_consent(root, client, by, note or None)
    elif action == "revoke":
        revoke_consent(root, client, by)
    else:
        raise DomainRefusal("consent action refused",
                            [f"unknown action '{action}'"])
    cfg = load_ai_config(root)
    return render(request, "fragments/consent_list.html", consent=list_consent(cfg))
