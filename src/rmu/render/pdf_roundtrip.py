"""Read-back verification for rendered PDFs (FR-013, research R8).

Runs on EVERY render, using the READING libraries (pypdf fields, pdfplumber
words) — an independent check on the writing path, in the SafeCard-honesty
spirit. A mismatch is a rendering failure surfaced as an exception, never a
warning.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
from pypdf import PdfReader

from rmu import store

#: positional tolerance (pt) for text-in-region checks (SC-005)
BBOX_TOLERANCE = 2.0

_CHECKBOX_TRUE = {"yes", "true", "1", "on", "x", "checked"}


@dataclass
class RoundTripReport:
    ok: bool = True
    mismatches: list[dict] = field(default_factory=list)

    def add(self, target_field: str, expected: str, got: str) -> None:
        self.ok = False
        self.mismatches.append(
            {"field": target_field, "expected": expected, "got": got}
        )


def _verify_form(config: dict, pdf_path: Path, record: dict) -> RoundTripReport:
    report = RoundTripReport()
    fields = PdfReader(pdf_path).get_fields() or {}
    for f in config["fields"]:
        expected = str(record.get(f["target_field"], ""))
        got = fields.get(f["field_id"])
        got_value = "" if got is None else str(got.value or "")
        if f["kind"] == "checkbox":
            expected_mark = "/Yes" if expected.lower() in _CHECKBOX_TRUE else "/Off"
            if got_value != expected_mark:
                report.add(f["target_field"], expected_mark, got_value)
        elif got_value != expected:
            report.add(f["target_field"], expected, got_value)
    return report


def _verify_overlay(config: dict, pdf_path: Path, record: dict) -> RoundTripReport:
    report = RoundTripReport()
    with pdfplumber.open(pdf_path) as pdf:
        for region in config["regions"]:
            page = pdf.pages[region["page"] - 1]
            x0, y0, x1, y1 = region["bbox"]
            # pdfplumber measures from the TOP; region bbox is PDF (bottom) coords
            top_min = float(page.height) - y1 - BBOX_TOLERANCE
            top_max = float(page.height) - y0 + BBOX_TOLERANCE
            expected = str(record.get(region["target_field"], ""))
            if region["kind"] == "text":
                words_in_region = [
                    w["text"]
                    for w in page.extract_words()
                    if x0 - BBOX_TOLERANCE <= w["x0"] <= x1 + BBOX_TOLERANCE
                    and top_min <= w["top"] <= top_max
                ]
                got = " ".join(words_in_region)
                if expected not in got:
                    report.add(region["target_field"], expected, got or "<empty region>")
            else:  # image presence + content (pixel-identical to the stored source)
                if not _image_in_region(pdf_path, region, expected):
                    report.add(
                        region["target_field"],
                        f"image {expected[:12]} in region {region['label']!r}",
                        "no matching embedded image",
                    )
    return report


def _image_in_region(pdf_path: Path, region: dict, sha: str) -> bool:
    from PIL import Image

    try:
        source = Image.open(io.BytesIO(store.get_bytes(sha))).convert("RGB")
    except FileNotFoundError:
        return False
    page = PdfReader(pdf_path).pages[region["page"] - 1]
    for embedded in page.images:
        try:
            candidate = embedded.image.convert("RGB")
        except Exception:
            continue
        if candidate.size == source.size and candidate.tobytes() == source.tobytes():
            return True
    return False


def verify(config: dict, pdf_path: Path, record: dict) -> RoundTripReport:
    """config = the registered template_files dict; mismatch list is exact."""
    if config["kind"] == "pdf_form":
        return _verify_form(config, Path(pdf_path), record)
    return _verify_overlay(config, Path(pdf_path), record)
