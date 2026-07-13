"""Fixed-layout overlay renderer (feature 003, D7/D10, FR-012/FR-012a).

Draws text values and record images at REGISTERED coordinates onto the
original template PDF: reportlab builds an overlay page (invariant mode,
real text so read-back works), pypdf merges it. Images scale to fit their
region preserving aspect ratio — never cropped, never stretched. Oversize
text and missing images are RenderProblems, never silent (FR-014).
"""

from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from rmu import store
from rmu.render.pdf_form import _FIXED_METADATA, RenderProblem

_FONT = "Helvetica"


def _text_problems(config: dict, record: dict) -> list[RenderProblem]:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    problems = []
    for region in config["regions"]:
        value = record.get(region["target_field"], "")
        if not value:
            problems.append(RenderProblem(
                region["target_field"], "missing_required",
                f"no value for registered region {region['label']!r}"))
            continue
        if region["kind"] == "text":
            size = region.get("font_size", 9)
            width = stringWidth(str(value), _FONT, size)
            x0, _, x1, _ = region["bbox"]
            if width > (x1 - x0):
                problems.append(RenderProblem(
                    region["target_field"], "oversize_value",
                    f"value {value!r} is wider than its registered region "
                    f"({width:.0f}pt > {x1 - x0:.0f}pt) - never truncated (D7)"))
        elif region["kind"] == "image":
            try:
                store.get_path(str(record[region["target_field"]]))
            except (FileNotFoundError, TypeError):
                problems.append(RenderProblem(
                    region["target_field"], "bad_image",
                    f"record image {record.get(region['target_field'])!r} "
                    f"not present in the store"))
    return problems


def render_overlay_pdf(config: dict, record: dict, out_path: Path) -> list[RenderProblem]:
    """Overlay one record onto the original PDF. Problems => no file written."""
    problems = _text_problems(config, record)
    if problems:
        return problems

    template = PdfReader(store.get_path(config["pdf_object"]))
    by_page: dict[int, list[dict]] = {}
    for region in config["regions"]:
        by_page.setdefault(region["page"], []).append(region)

    buffer = io.BytesIO()
    overlay = canvas.Canvas(buffer, invariant=1)  # research R9
    for page_no in range(1, len(template.pages) + 1):
        media = template.pages[page_no - 1].mediabox
        overlay.setPageSize((float(media.width), float(media.height)))
        for region in by_page.get(page_no, []):
            x0, y0, x1, y1 = region["bbox"]
            value = record[region["target_field"]]
            if region["kind"] == "text":
                size = region.get("font_size", 9)
                overlay.setFont(_FONT, size)
                text = str(value)
                if region.get("align") == "right":
                    overlay.drawRightString(x1 - 2, y0 + 3, text)
                elif region.get("align") == "center":
                    overlay.drawCentredString((x0 + x1) / 2, y0 + 3, text)
                else:
                    overlay.drawString(x0 + 2, y0 + 3, text)
            else:  # image: scale to fit, preserve aspect, centred (FR-012a)
                image = ImageReader(io.BytesIO(store.get_bytes(str(value))))
                overlay.drawImage(
                    image, x0, y0, width=x1 - x0, height=y1 - y0,
                    preserveAspectRatio=True, anchor="c",
                )
        overlay.showPage()
    overlay.save()
    buffer.seek(0)

    overlay_reader = PdfReader(buffer)
    writer = PdfWriter(clone_from=template)
    for i, page in enumerate(writer.pages):
        page.merge_page(overlay_reader.pages[i])
    writer.add_metadata(_FIXED_METADATA)
    with Path(out_path).open("wb") as fh:
        writer.write(fh)
    return []
