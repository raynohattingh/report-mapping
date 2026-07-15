"""Content-addressed PDF streaming for PDF.js panes (FR-010, FR-043)."""

from __future__ import annotations

import re

from fastapi import APIRouter
from fastapi.responses import FileResponse, Response

from rmu import store as blobstore

router = APIRouter()

_SHA = re.compile(r"^[0-9a-f]{64}$")


@router.get("/documents/{sha}/pdf")
def document_pdf(sha: str):
    if not _SHA.fullmatch(sha):
        return Response(status_code=404)
    try:
        path = blobstore.get_path(sha)
    except FileNotFoundError:
        return Response(status_code=404)
    return FileResponse(
        path, media_type="application/pdf",
        headers={"cache-control": "no-store"},  # FR-043: nothing persists browser-side
    )
