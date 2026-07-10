"""OPC/ZIP canonicalization (research R1): docx/xlsx are ZIP containers whose
writers stamp real datetimes into ZIP entries and core properties. Every
rendered OPC file passes through here so 'byte-identical' is a straight file
hash (FR-011, SC-004) — no masked comparisons, nowhere for drift to hide.

Canonical form: sorted entry names, fixed entry datetime (the 1980 ZIP epoch),
fixed compression, pinned dcterms:created/modified, empty lastModifiedBy.
"""

from __future__ import annotations

import io
import re
import zipfile

CANON_DATE = (1980, 1, 1, 0, 0, 0)
CANON_STAMP = "1980-01-01T00:00:00Z"


def _pin_core_props(xml: bytes) -> bytes:
    text = xml.decode("utf-8")
    for tag in ("dcterms:created", "dcterms:modified"):
        text = re.sub(
            rf"<{tag}[^>]*>[^<]*</{tag}>",
            f'<{tag} xsi:type="dcterms:W3CDTF">{CANON_STAMP}</{tag}>',
            text,
        )
    text = re.sub(
        r"<cp:lastModifiedBy>[^<]*</cp:lastModifiedBy>",
        "<cp:lastModifiedBy></cp:lastModifiedBy>",
        text,
    )
    text = re.sub(r"<cp:revision>[^<]*</cp:revision>", "<cp:revision>1</cp:revision>", text)
    return text.encode("utf-8")


def canonicalize_opc(data: bytes) -> bytes:
    """Rewrite an OPC (docx/xlsx) package into canonical byte form."""
    with zipfile.ZipFile(io.BytesIO(data)) as zin:
        names = sorted(zin.namelist())
        contents = {name: zin.read(name) for name in names}
    if "docProps/core.xml" in contents:
        contents["docProps/core.xml"] = _pin_core_props(contents["docProps/core.xml"])
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zout:
        for name in names:
            info = zipfile.ZipInfo(name, date_time=CANON_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            zout.writestr(info, contents[name])
    return out.getvalue()
