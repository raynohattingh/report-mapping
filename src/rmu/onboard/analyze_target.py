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

_LABEL_RE = re.compile(r"^([A-Z][A-Za-z ]{1,30}:)\s*$")
_REQUIRED_FLAG = 2  # AcroForm /Ff bit 1 (value 2) = required

_FT_KINDS = {"/Tx": "text", "/Ch": "choice", "/Btn": "checkbox"}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _element(eid, kind, confidence, evidence, payload, flags=None) -> dict:
    e = {
        "id": eid,
        "element_kind": kind,
        "confidence": round(min(confidence, 0.99), 2),
        "evidence": evidence,
        "review_state": "proposed",
        "payload": payload,
    }
    if flags:
        e["flags"] = flags
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
