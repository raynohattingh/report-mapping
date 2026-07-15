"""Apply-to-exemplar preview routes (US2, FR-030/FR-030a) — thin delegates.

The artifact is produced by rmu.mapping.preview.build_preview — the exact
function `rmu map preview` calls — then displayed natively: PDF inline via
PDF.js, CSV as a table with flagged unresolved cells, docx as the real file to
open locally. Never an HTML approximation of a non-HTML target.
"""

from __future__ import annotations

import csv as _csv

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, Response

from rmu.mapping.preview import build_preview
from rmu.studio.app import DomainRefusal
from rmu.studio.routes.common import db_session, render

router = APIRouter()

_MEDIA = {
    "csv": "text/csv",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf_form": "application/pdf",
    "pdf_overlay": "application/pdf",
}


def _build(session_id: int):
    with db_session() as s:
        try:
            return build_preview(s, session_id)
        except LookupError as err:
            raise DomainRefusal("unknown session", [str(err)]) from err


@router.post("/sessions/{session_id}/preview")
def preview(request: Request, session_id: int):
    result = _build(session_id)
    table = None
    if result.kind == "csv":
        with result.out_path.open(newline="", encoding="utf-8") as fh:
            table = list(_csv.reader(fh))
    return render(
        request, "fragments/preview.html", session_id=session_id,
        result=result, table=table,
        file_url=f"/sessions/{session_id}/preview/file",
        filename=result.out_path.name,
    )


@router.get("/sessions/{session_id}/preview/file")
def preview_file(session_id: int):
    result = _build(session_id)  # rebuild = always the current draft's output
    if not result.out_path.exists():
        return Response(status_code=404)
    return FileResponse(
        result.out_path, media_type=_MEDIA.get(result.kind, "application/octet-stream"),
        filename=result.out_path.name,
        headers={"cache-control": "no-store"},  # FR-043
    )
