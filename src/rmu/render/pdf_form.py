"""AcroForm fill renderer (feature 003, D7/D10, FR-011/FR-015).

Fills a registered pdf_form TargetTemplate field-by-field from resolved
record values. Deterministic: fixed metadata, no clock (research R9).
Values never guessed: a missing required value or an over-length value is a
RenderProblem for the exceptions report, never truncation (FR-014).
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject

from rmu import store

#: pinned metadata: byte-identical re-runs (FR-015, "timestamps excepted" is
#: honored by pinning them to a constant, research R9)
_FIXED_METADATA = {"/Producer": "rmu", "/CreationDate": "D:20260101000000Z"}

_CHECKBOX_TRUE = {"yes", "true", "1", "on", "x", "checked"}


class RenderProblem(Exception):
    """One record's value cannot be rendered honestly (FR-014)."""

    def __init__(self, field: str, kind: str, reason: str):
        self.field = field
        self.kind = kind  # missing_required | oversize_value | bad_image
        self.reason = reason
        super().__init__(f"{field}: {reason}")


def _collect_problems(config: dict, record: dict) -> list[RenderProblem]:
    problems = []
    for f in config["fields"]:
        value = record.get(f["target_field"], "")
        if not value:
            problems.append(RenderProblem(
                f["target_field"], "missing_required",
                f"no value for required form field {f['field_id']!r}"))
            continue
        max_len = f.get("max_len")
        if max_len and f["kind"] == "text" and len(str(value)) > max_len:
            problems.append(RenderProblem(
                f["target_field"], "oversize_value",
                f"value {value!r} exceeds field max length {max_len} "
                f"(never truncated - fix the mapping or the template)"))
        if f.get("options") and str(value) not in f["options"]:
            problems.append(RenderProblem(
                f["target_field"], "oversize_value",
                f"value {value!r} not among the form's fixed options {f['options']}"))
    return problems


def render_form_pdf(config: dict, record: dict, out_path: Path) -> list[RenderProblem]:
    """Fill one output PDF from one record. Returns problems (empty = clean);
    on problems NO file is written — exceptions, not half-filled forms."""
    problems = _collect_problems(config, record)
    if problems:
        return problems

    reader = PdfReader(store.get_path(config["pdf_object"]))
    writer = PdfWriter(clone_from=reader)
    values: dict[str, str] = {}
    for f in config["fields"]:
        raw = str(record[f["target_field"]])
        if f["kind"] == "checkbox":
            values[f["field_id"]] = "/Yes" if raw.lower() in _CHECKBOX_TRUE else "/Off"
        else:
            values[f["field_id"]] = raw
    for page in writer.pages:
        writer.update_page_form_field_values(page, values, auto_regenerate=False)
    # viewers regenerate appearances; read-back is unaffected (research R1)
    if writer._root_object.get("/AcroForm") is not None:
        writer._root_object["/AcroForm"][NameObject("/NeedAppearances")] = (
            __import__("pypdf").generic.BooleanObject(True)
        )
    writer.add_metadata(_FIXED_METADATA)
    with Path(out_path).open("wb") as fh:
        writer.write(fh)
    return []
