"""T039: two renders of the same content with different embedded timestamps
canonicalize to identical bytes (research R1)."""

import datetime
import io

from docxtpl import DocxTemplate

from rmu.render.canonicalize import canonicalize_opc

TEMPLATE = "templates/interim.annexc_pack/pack_template.docx"

CONTEXT = {
    "inspection_name": "Canon test",
    "inspection_date": "2026-07-11",
    "contract_number": "X-1",
    "inspection_method": "UAV visual",
    "company": "Synthetic Ops",
    "findings": [
        {"finding_id": "1", "defect_code": "C1", "priority": "P1",
         "source_severity": "5", "comments": "burned lead"},
    ],
}


def _render_with_created(created: datetime.datetime) -> bytes:
    tpl = DocxTemplate(TEMPLATE)
    tpl.render(dict(CONTEXT))
    tpl.docx.core_properties.created = created
    tpl.docx.core_properties.modified = created
    tpl.docx.core_properties.last_modified_by = f"writer-{created.year}"
    buf = io.BytesIO()
    tpl.save(buf)
    return buf.getvalue()


def test_timestamps_cannot_leak_into_canonical_output():
    a = _render_with_created(datetime.datetime(2020, 1, 1, 8, 0, 0))
    b = _render_with_created(datetime.datetime(2026, 12, 31, 23, 59, 59))
    assert a != b  # raw renders differ (embedded timestamps)
    assert canonicalize_opc(a) == canonicalize_opc(b)  # canonical bytes identical


def test_canonicalization_is_idempotent():
    a = _render_with_created(datetime.datetime(2021, 6, 1))
    once = canonicalize_opc(a)
    assert canonicalize_opc(once) == once
