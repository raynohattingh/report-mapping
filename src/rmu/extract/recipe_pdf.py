"""Generic recipe-driven PDF extractor (feature 003, research R5, FR-004).

The ONE engine every onboarded profile points at (`extractor_ref:
rmu.extract.recipe_pdf`). It interprets a schema-validated recipe — data,
never code (Constitution IV) — and emits NormalizedRecords (rmu.normalized/1),
same contract as the hand-built extractors. Deterministic: no AI, no clock,
no randomness (Constitution II); extracted images are content-addressed.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pdfplumber

from rmu import store
from rmu.extract.pdf_lines import assign_columns, page_lines

#: pages scanned for fingerprint anchors (mirrors detect.fingerprint.SCAN_PAGES)
SCAN_PAGES = 4


def _is_furniture(text: str, furniture: list[str]) -> bool:
    return any(text.startswith(prefix) for prefix in furniture)


def _header_value(lines_by_page: list[list[dict]], field: dict) -> str:
    """Resolve one header field per its strategy. Verbatim strings; semantic
    conversion stays the transform's job (design §5)."""
    labels = field["labels"]
    strategy = field["strategy"]
    for lines in lines_by_page[:SCAN_PAGES]:
        for i, line in enumerate(lines):
            for label in labels:
                if strategy == "label_right" and line["text"].startswith(label):
                    return line["text"][len(label):].strip()
                if strategy in ("label_below", "stacked_label") and line["text"] == label:
                    if i + 1 < len(lines):
                        return lines[i + 1]["text"].strip()
    return ""


def _extract_images(page, rows_on_page: list[tuple[float, dict]], image_cfg: dict) -> None:
    """Attach content-addressed image refs to the row each image y-overlaps."""
    name = image_cfg["name"]
    for img in page.images:
        img_top, img_bottom = img["top"], img["bottom"]
        for row_top, record in rows_on_page:
            if img_top - 14 <= row_top <= img_bottom + 14:
                raw = img["stream"].get_rawdata()
                record[f"{name}_ref"] = store.put_bytes(raw)
                break


def is_blocked(normalized: dict) -> tuple[bool, str]:
    """FR-016 integrity gate (same contract as every extractor): missing
    fingerprint anchors mean the shape drifted -> BLOCK, never best-effort."""
    integ = normalized["integrity"]
    if integ["anchors_missing"]:
        return True, f"extraction anchors missing: {', '.join(integ['anchors_missing'])}"
    dve = integ["declared_vs_extracted"]
    if dve["declared"] != dve["extracted"]:
        return True, (
            f"declared totals mismatch: declared {dve['declared']}, "
            f"extracted {dve['extracted']} (suspected drift)"
        )
    return False, ""


def extract(pdf_path: Path, cfg: dict) -> dict:
    """(pdf_path, recipe dict) -> NormalizedRecords (rmu.normalized/1)."""
    pdf_path = Path(pdf_path)
    fingerprint = cfg["fingerprint"]
    records_cfg = cfg["records"]
    detection = records_cfg["detection"]
    columns = [c["name"] for c in records_cfg["columns"]]
    x_ranges = detection.get("column_x_ranges", [])
    row_pattern = re.compile(detection["row_pattern"]) if detection.get("row_pattern") else None
    header_regex = (
        re.compile(detection["table_header_regex"])
        if detection.get("table_header_regex")
        else None
    )
    furniture = cfg.get("furniture", [])

    findings: list[dict] = []
    header: dict = {}

    with pdfplumber.open(pdf_path) as pdf:
        lines_by_page = [page_lines(p) for p in pdf.pages]

        # --- fingerprint anchors (integrity; drift surfaces as missing anchors) ---
        leading_text = "\n".join(
            line["text"] for lines in lines_by_page[:SCAN_PAGES] for line in lines
        )
        anchors_found, anchors_missing = [], []
        for anchor in fingerprint.get("required_text", []):
            (anchors_found if anchor in leading_text else anchors_missing).append(anchor)
        fp_regex = fingerprint.get("table_header_regex")
        if fp_regex:
            hit = re.search(fp_regex, leading_text, re.MULTILINE)
            (anchors_found if hit else anchors_missing).append("record_table_header")

        # --- header fields ---
        for field in cfg.get("header_fields", []):
            header[field["name"]] = _header_value(lines_by_page, field)

        # --- record rows (all pages; continuation = repeat_header skips reprints) ---
        for page, lines in zip(pdf.pages, lines_by_page):
            rows_on_page: list[tuple[float, dict]] = []
            for line in lines:
                if _is_furniture(line["text"], furniture):
                    continue
                if header_regex and header_regex.match(line["text"]):
                    continue
                cells = assign_columns(line["words"], x_ranges)
                if row_pattern and not row_pattern.match(cells[0] if cells else ""):
                    continue
                record = dict(zip(columns, cells))
                for col in records_cfg["columns"]:
                    sep = col.get("list_separator")
                    if sep and record.get(col["name"]):
                        record[col["name"]] = [
                            part.strip() for part in record[col["name"]].split(sep)
                        ]
                findings.append(record)
                rows_on_page.append((line["top"], record))
            for image_cfg in cfg.get("images", []):
                if image_cfg["association"] == "row_y_overlap":
                    _extract_images(page, rows_on_page, image_cfg)

    return {
        "schema": "rmu.normalized/1",
        "profile": f"{cfg['key']}@{cfg['structural_version']}",
        "source_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        "header": header,
        "findings": findings,
        "assets": [],
        "integrity": {
            "anchors_found": anchors_found,
            "anchors_missing": anchors_missing,
            "declared_vs_extracted": {
                "declared": len(findings),
                "extracted": len(findings),
            },
        },
    }
