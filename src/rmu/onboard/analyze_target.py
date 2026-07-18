"""Target-format PDF analysis -> draft template proposal (FR-006/007/008/025).

Fillable form: AcroForm fields enumerate into a proposed field schema — the
PDF's OWN declarations (required flags, kinds, options, max lengths) arrive as
`pdf_declared` evidence (FR-025); the analyst adjusts and adds business rules
in review. Fixed layout: label-adjacent boxes (page rects) become proposed
regions with page coordinates; large boxes propose image kind, undersized
image regions get the `region_too_small` flag. The kind ladder (pdf_kind)
runs before this module — encrypted/XFA/scanned never reach it.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pdfplumber
from pypdf import PdfReader

#: an image region narrower/shorter than this is flagged region_too_small (pt)
MIN_IMAGE_REGION = 40
#: a box at least this tall is proposed as an image region, not text
IMAGE_HEIGHT_THRESHOLD = 40
#: a grid cell narrower/shorter than this cannot hold a value (pt)
GRID_MIN_CELL_W = 12
GRID_MIN_CELL_H = 8
#: the whole point is line-drawn grids: reconstruct cells from line strokes
_GRID_TABLE_SETTINGS = {"vertical_strategy": "lines", "horizontal_strategy": "lines"}

_LABEL_RE = re.compile(r"^([A-Z][A-Za-z ]{1,30}:)\s*$")
_REQUIRED_FLAG = 2  # AcroForm /Ff bit 1 (value 2) = required

_FT_KINDS = {"/Tx": "text", "/Ch": "choice", "/Btn": "checkbox"}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


LOW_CONFIDENCE_FLOOR = 0.5  # spec edge case: below this, flagged for attention


def _element(eid, kind, confidence, evidence, payload, flags=None) -> dict:
    e = {
        "id": eid,
        "element_kind": kind,
        "confidence": round(min(confidence, 0.99), 2),
        "evidence": evidence,
        "review_state": "proposed",
        "payload": payload,
    }
    flags = list(flags or [])
    if e["confidence"] < LOW_CONFIDENCE_FLOOR:
        flags.append("low_confidence")  # never silently pre-confirmed
    if flags:
        e["flags"] = sorted(set(flags))
    return e


def _form_elements(pdf_path: Path) -> list[dict]:
    fields = PdfReader(pdf_path).get_fields() or {}
    elements = []
    for i, (name, f) in enumerate(sorted(fields.items())):
        name = str(name)  # plain str: pypdf generics don't YAML-serialize
        kind = _FT_KINDS.get(str(f.get("/FT")), "text")
        flags_int = int(f.get("/Ff") or 0)
        payload: dict = {
            "field_id": name,
            "target_field": _slug(name),
            "kind": kind,
            "required": bool(flags_int & _REQUIRED_FLAG),
        }
        options = f.get("/Opt")
        if options:
            payload["kind"] = "choice"
            payload["options"] = [
                str(o[1] if isinstance(o, list) else o) for o in options
            ]
        max_len = f.get("/MaxLen")
        if max_len:
            payload["max_len"] = int(max_len)
        elements.append(_element(
            f"fld-{i}", "form_field",
            0.95,  # the PDF itself declares these - highest structural evidence
            {"pages": [1], "source": "pdf_declared"},
            payload,
        ))
    return elements


def _fixed_layout_elements(pdf_path: Path) -> list[dict]:
    from rmu.extract.pdf_lines import page_lines

    elements = []
    counter = 0
    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            height = float(page.height)
            rects = [r for r in page.rects if r["width"] > 20 and r["height"] > 8]
            segments: list[tuple[str, float, float]] = []  # (text, x1, top)
            for line in page_lines(page):
                # labels can share a visual line (e.g. a photo box header right
                # of a field label): split the line into x-gap segments
                run: list[dict] = []
                for word in line["words"]:
                    if run and word["x0"] - run[-1]["x1"] > 30:
                        segments.append((
                            " ".join(w["text"] for w in run), run[-1]["x1"], line["top"]
                        ))
                        run = []
                    run.append(word)
                if run:
                    segments.append((
                        " ".join(w["text"] for w in run), run[-1]["x1"], line["top"]
                    ))
            for text, label_x1, label_top in segments:
                m = re.match(r"^([A-Z][A-Za-z ]{1,30}:)$", text)
                if not m:
                    continue
                label = m.group(1)
                # nearest rect right of OR below the label
                candidates = sorted(
                    rects,
                    key=lambda r: (
                        abs(r["top"] - label_top) + max(0.0, label_x1 - r["x0"])
                    ),
                )
                box = next(
                    (r for r in candidates
                     if r["x0"] >= label_x1 - 10 or r["top"] > label_top + 5),
                    None,
                )
                if box is None:
                    continue
                bbox = [
                    round(box["x0"], 1),
                    round(height - box["bottom"], 1),
                    round(box["x1"], 1),
                    round(height - box["top"], 1),
                ]
                is_image = box["height"] >= IMAGE_HEIGHT_THRESHOLD
                flags = None
                if is_image and (
                    box["width"] < MIN_IMAGE_REGION or box["height"] < MIN_IMAGE_REGION
                ):
                    flags = ["region_too_small"]
                elements.append(_element(
                    f"rgn-{counter}", "overlay_region",
                    0.8,  # box-anchored: strong geometry evidence
                    {"pages": [page_no], "source": "heuristic"},
                    {"label": label,
                     "target_field": _slug(label),
                     "kind": "image" if is_image else "text",
                     "page": page_no,
                     "bbox": bbox},
                    flags=flags,
                ))
                counter += 1
                rects.remove(box)
    if not elements:
        # No label+box pairs found: grid form. Prefer 2-D axis reconstruction
        # (feature 005); fall back to the flat per-cell path only if no
        # reconstructable grid is present.
        from rmu.onboard.matrix import reconstruct_matrix

        matrix = reconstruct_matrix(pdf_path)
        if matrix is not None:
            return matrix
        return _grid_region_elements(pdf_path)
    return elements


def _grid_region_elements(pdf_path: Path) -> list[dict]:
    """Fallback for line-drawn grid forms (e.g. inspection checklists): the
    label+box pass sees only 1pt hairline rects and finds nothing, yet the
    fillable areas are the grid's blank cells. Reconstruct cells from line
    strokes and propose every blank, size-valid cell as an overlay region,
    named best-effort from its row label, else column header, else position —
    the analyst renames in review (design 2026-07-14, grid-region spec)."""
    elements: list[dict] = []
    used: dict[str, int] = {}
    counter = 0
    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            height = float(page.height)
            for table in page.find_tables(table_settings=_GRID_TABLE_SETTINGS):
                text = table.extract()

                def cell_text(i: int, j: int, text=text) -> str:
                    try:
                        value = text[i][j]
                    except (IndexError, TypeError):
                        value = None
                    return " ".join((value or "").split())

                for i, row in enumerate(table.rows):
                    for j, cell in enumerate(row.cells):
                        if cell is None:  # merged/absent cell
                            continue
                        x0, top, x1, bottom = cell
                        if x1 - x0 < GRID_MIN_CELL_W or bottom - top < GRID_MIN_CELL_H:
                            continue
                        if cell_text(i, j):
                            continue  # pre-printed cell, not fillable
                        label, association = "", "positional"
                        for jj in range(j - 1, -1, -1):  # nearest left in row
                            if cell_text(i, jj):
                                label, association = cell_text(i, jj), "row_label"
                                break
                        if not label:
                            for ii in range(i - 1, -1, -1):  # nearest above in col
                                if cell_text(ii, j):
                                    label, association = cell_text(ii, j), "col_header"
                                    break
                        label = label[:60]
                        slug = _slug(label)
                        if not slug:  # no context anywhere (or non-text glyphs)
                            slug = f"cell_p{page_no}_r{i}_c{j}"
                            label, association = slug, "positional"
                        used[slug] = used.get(slug, 0) + 1
                        if used[slug] > 1:
                            slug = f"{slug}_{used[slug]}"
                        elements.append(_element(
                            f"rgn-{counter}", "overlay_region",
                            0.6,  # geometry-reconstructed; weaker than a labeled box
                            {"pages": [page_no], "source": "heuristic",
                             "association": association, "row": i, "col": j},
                            {"label": label,
                             "target_field": slug,
                             "kind": "text",
                             "page": page_no,
                             "bbox": [round(x0, 1), round(height - bottom, 1),
                                      round(x1, 1), round(height - top, 1)]},
                        ))
                        counter += 1
    return elements


def analyze(target: Path, *, kind: str) -> dict:
    """Target PDF -> draft template proposal document. `kind` comes from the
    pdf_kind ladder ('form' | 'fixed_layout')."""
    target = Path(target)
    if kind == "form":
        elements = _form_elements(target)
    else:
        elements = _fixed_layout_elements(target)
    # cardinality is data the analyst declares (clarification 2026-07-12);
    # per_record is the primary case, proposed for review like everything else
    elements.append(_element(
        "card-0", "cardinality", 0.5,
        {"pages": [1], "source": "heuristic"},
        {"cardinality": "per_record"},
    ))
    return {
        "kind": "template",
        "exemplars": [hashlib.sha256(target.read_bytes()).hexdigest()],
        "elements": elements,
    }
