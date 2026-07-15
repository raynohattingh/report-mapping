"""Apply-to-exemplar preview — the single preview path (FR-008/FR-030).

Extracted from the `rmu map preview` Typer body (feature 004, research.md R4)
so the CLI and studio previews are the same bytes by construction. Non-strict
resolve: unresolvable cells become visible `<<unresolved>>`-style markers,
never guesses; render problems surface, never absorbed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from rmu import store as blobstore
from rmu.apply.engine import resolve_record
from rmu.mapping.loader import parse_transform
from rmu.mapping.start import load_session_state
from rmu.registry import get_template_by_id, load_value_maps, template_meta
from rmu.render.csv import render_csv


@dataclass
class PreviewResult:
    kind: str                      # docx | csv | pdf_form | pdf_overlay
    out_path: Path                 # the actual artifact, in store/drafts
    rows: list = field(default_factory=list)   # resolved per-finding values
    header_values: dict = field(default_factory=dict)
    unresolved: int = 0
    columns: list = field(default_factory=list)   # csv only
    render_problems: list = field(default_factory=list)  # pdf kinds (FR-030)


def build_preview(s: Session, session_id: int) -> PreviewResult:
    """Render the exemplar through the current draft INTO ITS TARGET FORMAT."""
    ms, draft_path, doc_row = load_session_state(s, session_id)
    doc = parse_transform(draft_path.read_text(encoding="utf-8"))
    normalized = json.loads(blobstore.get_bytes(doc_row.extraction_ref))
    template_row = get_template_by_id(s, ms.target_template_id)
    meta = template_meta(template_row)
    vmaps = load_value_maps(s, doc)

    prompt_placeholders = {
        p["key"]: f"<<{p['key']}>>" for p in doc.get("prompts", [])
    }
    problems_total = 0

    if meta["kind"] == "docx":
        from rmu.render.docx import render_pack

        schema = template_row.required_schema
        header_ctx = {"header": normalized["header"], "finding": {},
                      "prompt": prompt_placeholders}
        header_fields = list(schema.get("required", [])) + list(
            schema.get("optional", [])
        )
        values, problems = resolve_record(
            header_fields, doc, header_ctx, vmaps, strict=False
        )
        problems_total += len(problems)
        rows = []
        for finding in normalized["findings"]:
            context = {"header": normalized["header"], "finding": finding,
                       "prompt": prompt_placeholders}
            row, problems = resolve_record(
                list(schema.get("finding_fields", [])), doc, context, vmaps,
                strict=False,
            )
            problems_total += len(problems)
            rows.append(row)
        template_bytes = blobstore.get_bytes(template_row.template_files[meta["file"]])
        out = blobstore.drafts_dir() / f"session_{session_id}.preview.docx"
        out.write_bytes(render_pack(template_bytes, {**values, "findings": rows}))
        return PreviewResult(kind="docx", out_path=out, rows=rows,
                             header_values=values, unresolved=problems_total)

    if meta["kind"] in ("pdf_form", "pdf_overlay"):
        return _preview_pdf(session_id, meta, template_row, doc, normalized,
                            vmaps, prompt_placeholders)

    columns = meta.get("columns") or list(template_row.required_schema["required"])
    rows = []
    for finding in normalized["findings"]:
        context = {"header": normalized["header"], "finding": finding,
                   "prompt": prompt_placeholders}
        values, problems = resolve_record(columns, doc, context, vmaps, strict=False)
        problems_total += len(problems)
        rows.append(values)
    out = blobstore.drafts_dir() / f"session_{session_id}.preview.csv"
    out.write_bytes(render_csv(rows, columns))
    return PreviewResult(kind="csv", out_path=out, rows=rows,
                         unresolved=problems_total, columns=columns)


def _preview_pdf(session_id, meta, template_row, doc, normalized, vmaps,
                 prompt_placeholders) -> PreviewResult:
    """PDF-kind targets (003, D7): first finding rendered through the REAL
    renderer — the same output an ApplyRun writes (FR-030a: never a lookalike).

    Render problems (oversize value, missing image, round-trip mismatch) are
    reported verbatim; a problem-blocked render still returns the resolved
    values so the analyst can see what mapped."""
    if meta["kind"] == "pdf_form":
        from rmu.render.pdf_form import render_form_pdf as render_pdf

        target_fields = [f["target_field"] for f in meta["fields"]]
    else:
        from rmu.render.pdf_overlay import render_overlay_pdf as render_pdf

        target_fields = [r["target_field"] for r in meta["regions"]]

    findings = normalized["findings"] or [{}]
    context = {"header": normalized["header"], "finding": findings[0],
               "prompt": prompt_placeholders}
    values, problems = resolve_record(target_fields, doc, context, vmaps,
                                      strict=False)
    out = blobstore.drafts_dir() / f"session_{session_id}.preview.pdf"
    render_problems = render_pdf(meta, values, out)  # problems => no file written
    return PreviewResult(
        kind=meta["kind"], out_path=out, rows=[values],
        unresolved=len(problems),
        render_problems=[{"field": p.field, "kind": p.kind, "reason": p.reason}
                         for p in render_problems],
    )
