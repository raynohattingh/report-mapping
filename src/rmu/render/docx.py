"""docxtpl rendering for the INTERIM annexc pack — always canonicalized
(research R1) so batch determinism holds for OPC outputs too."""

from __future__ import annotations

import io

from docxtpl import DocxTemplate

from rmu.render.canonicalize import canonicalize_opc


def render_pack(template_bytes: bytes, context: dict) -> bytes:
    tpl = DocxTemplate(io.BytesIO(template_bytes))
    tpl.render(dict(context))
    buf = io.BytesIO()
    tpl.save(buf)
    return canonicalize_opc(buf.getvalue())
