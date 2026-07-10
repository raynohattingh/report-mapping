"""Extractor for profile scopito.pdf.powerline.v2020 -> NormalizedRecords
(contracts/normalized-records.md).

Label-anchored + word-position based so both 2020 layout variants parse (A1):
header values are the nearest number BELOW a label word with x-overlap;
annotation-table cells are grouped by column x-boundaries (from the header
words) and row bands (midpoints between consecutive Id-word tops), which
handles vertically-centered wrapped Comments cells.

Strings are extracted verbatim (trimmed); semantic conversion is the
transform's job (Constitution VI, design §5). Record-level parse problems get
a `parse_error` marker and become per-record exceptions downstream; structural
problems land in `integrity` and BLOCK the document upstream of Apply (FR-016).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pdfplumber

DATE_RE = re.compile(r"[A-Z][a-z]{2,8} \d{1,2}, \d{4}")
FOOTER_RE = re.compile(r"^\d+ / \d+$")


def _x_overlap(a, b) -> float:
    return min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])


def _nearest_number_below(words: list[dict], label: dict, max_dy: float = 60) -> int | None:
    best = None
    for w in words:
        if not w["text"].isdigit():
            continue
        dy = w["top"] - label["top"]
        if dy <= 2 or dy > max_dy:
            continue
        if _x_overlap(label, w) <= 0:
            continue
        if best is None or dy < best[0]:
            best = (dy, int(w["text"]))
    return best[1] if best else None


def _words_near_label(words: list[dict], label: dict, max_dy: float = 25) -> str:
    """Best-effort value text below/right of a label (Type:/Company: fields)."""
    picked = [
        w
        for w in words
        if 2 < w["top"] - label["top"] <= max_dy
        and label["x0"] - 15 <= w["x0"] <= label["x0"] + 140
    ]
    picked.sort(key=lambda w: (w["top"], w["x0"]))
    return " ".join(w["text"] for w in picked).strip()


def _find_label(words: list[dict], variants: list[str]) -> dict | None:
    for w in words:
        if w["text"] in variants:
            return w
    return None


def _first_line(page) -> str:
    text = page.extract_text() or ""
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _split_cell(cell: str, sep: str) -> list[str]:
    return [part.strip() for part in cell.split(sep) if part.strip()]


def _parse_table_page(page, cfg: dict, vocab: set[str]) -> tuple[list[dict], bool]:
    """Return (findings, header_found) for one annotation-table page."""
    table_cfg = cfg["annotation_table"]
    sep = table_cfg["list_separator"]
    id_re = re.compile(table_cfg["id_pattern"])
    words = page.extract_words()

    # Locate the header row: an 'Id' word whose line also has 'Severity' and 'Page'.
    header_words: dict[str, dict] = {}
    header_top = None
    for w in words:
        if w["text"] != "Id":
            continue
        line = [v for v in words if abs(v["top"] - w["top"]) < 3]
        texts = {v["text"] for v in line}
        if "Severity" in texts and "Page" in texts:
            header_top = w["top"]
            for v in line:
                header_words[v["text"]] = v
            break
    if header_top is None:
        return [], False

    # Column anchors in declared order; 'User tags' contributes its first word.
    col_names, col_anchors = [], []
    for name in table_cfg["columns"]:
        anchor = header_words.get(name.split()[0])
        if anchor is None:
            if name in table_cfg.get("optional_columns", []):
                continue
            return [], False
        col_names.append(name)
        col_anchors.append(anchor)
    # Cells are center-aligned per column, so column edges are the midpoints
    # between adjacent header words (values may start left of the header x0).
    edges = [0.0]
    for a, b in zip(col_anchors, col_anchors[1:]):
        edges.append((a["x1"] + b["x0"]) / 2)
    edges.append(float(page.width))
    bounds = list(zip(edges, edges[1:]))

    def col_of(word) -> str | None:
        for name, (lo, hi) in zip(col_names, bounds):
            if lo <= word["x0"] < hi:
                return name
        return None

    # Words below the header, minus the page footer ("n / m").
    footer_tops = {
        w["top"]
        for w in words
        if FOOTER_RE.match(
            " ".join(v["text"] for v in words if abs(v["top"] - w["top"]) < 3)
        )
    }
    body = [
        w
        for w in words
        if w["top"] > header_top + 5 and all(abs(w["top"] - ft) >= 3 for ft in footer_tops)
    ]

    id_words = sorted(
        (w for w in body if col_of(w) == "Id" and id_re.match(w["text"])),
        key=lambda w: w["top"],
    )
    if not id_words:
        return [], True

    # Row bands: midpoints between consecutive Id tops (centered wrapped cells).
    band_edges = [header_top + 5]
    for a, b in zip(id_words, id_words[1:]):
        band_edges.append((a["top"] + b["top"]) / 2)
    band_edges.append(float(page.height))

    findings = []
    for i, idw in enumerate(id_words):
        lo, hi = band_edges[i], band_edges[i + 1]
        cells: dict[str, list] = {name: [] for name in col_names}
        for w in body:
            if lo <= w["top"] < hi and w is not idw:
                c = col_of(w)
                if c:
                    cells[c].append(w)
        joined = {
            name: " ".join(
                v["text"] for v in sorted(ws, key=lambda x: (round(x["top"]), x["x0"]))
            ).strip()
            for name, ws in cells.items()
        }
        # Severity is a single token; anything extra physically belongs to the
        # neighbouring User-tags cell (its text can start left of the column
        # midpoint on some rows).
        severity_tokens = joined.get("Severity", "").split()
        severity = severity_tokens[0] if severity_tokens else ""
        overflow = " ".join(severity_tokens[1:])
        tags_text = joined.get("User tags", "")
        if overflow:
            tags_text = f"{overflow} {sep} {tags_text}" if tags_text else overflow
        page_text = joined.get("Page", "")
        page_num = int(page_text) if page_text.isdigit() else None
        record = {
            "id": idw["text"],
            "severity": severity,
            "user_tags": _split_cell(tags_text, sep),
            "issues": _split_cell(joined.get("Issues", ""), sep),
            "comments": joined.get("Comments", ""),
            "page": page_num,
        }
        if severity not in vocab:
            record["parse_error"] = f"severity {severity!r} outside vocabulary"
        elif page_num is None:
            record["parse_error"] = f"page column unparseable: {page_text!r}"
        findings.append(record)
    return findings, True


def extract(pdf_path: Path, cfg: dict) -> dict:
    pdf_path = Path(pdf_path)
    data = pdf_path.read_bytes()
    header_cfg = cfg["header"]
    vocab = set(cfg["severity_vocabulary"])
    detail_marker = cfg["detail_page"]["marker"]

    anchors_found: list[str] = []
    anchors_missing: list[str] = []
    header = {
        "inspection_name": "",
        "report_date": "",
        "inspection_type": "",
        "company": "",
        "declared_counts": {"images": None, "annotations": None},
    }
    findings: list[dict] = []
    assets: list[dict] = []
    table_header_found = False

    with pdfplumber.open(pdf_path) as pdf:
        pages = list(pdf.pages)
        texts = [p.extract_text() or "" for p in pages]

        header_idx = next(
            (i for i, t in enumerate(texts) if "Severity overview" in t), None
        )
        overview_idx = next(
            (i for i, t in enumerate(texts) if "Annotation overview" in t), None
        )
        detail_idxs = [i for i, t in enumerate(texts) if detail_marker in t]

        # --- header block ---
        if header_idx is not None:
            text = texts[header_idx]
            words = pages[header_idx].extract_words()

            date_label = header_cfg["date_label"]
            if date_label in text:
                anchors_found.append("header_block")
                m = DATE_RE.search(text[text.index(date_label):])
                header["report_date"] = m.group(0) if m else ""
            else:
                anchors_missing.append("header_block")

            sev_tokens = header_cfg["severity_row_tokens"]
            if all(tok in text for tok in sev_tokens):
                anchors_found.append("severity_overview")
            else:
                anchors_missing.append("severity_overview")

            ann_label = _find_label(words, header_cfg["annotations_labels"])
            img_label = _find_label(words, header_cfg["images_labels"])
            if ann_label is not None:
                header["declared_counts"]["annotations"] = _nearest_number_below(
                    words, ann_label
                )
            if img_label is not None:
                header["declared_counts"]["images"] = _nearest_number_below(words, img_label)
            if header["declared_counts"]["annotations"] is None:
                anchors_missing.append("declared_totals")
            else:
                anchors_found.append("declared_totals")

            type_label = _find_label(words, [header_cfg["type_label"]])
            if type_label is not None:
                header["inspection_type"] = _words_near_label(words, type_label)
            company_label = _find_label(words, [header_cfg["company_label"]])
            if company_label is not None:
                header["company"] = _words_near_label(words, company_label)
        else:
            anchors_missing.extend(["header_block", "severity_overview", "declared_totals"])

        # --- inspection name: first line of first detail page, else header page ---
        if detail_idxs:
            header["inspection_name"] = _first_line(pages[detail_idxs[0]])
        elif header_idx is not None:
            header["inspection_name"] = _first_line(pages[header_idx])

        # --- annotation table: overview page up to the first detail page ---
        if overview_idx is not None:
            stop = detail_idxs[0] if detail_idxs else len(pages)
            for i in range(overview_idx, stop):
                page_findings, found = _parse_table_page(pages[i], cfg, vocab)
                table_header_found = table_header_found or found
                findings.extend(page_findings)
        if table_header_found:
            anchors_found.append("annotation_table")
        else:
            anchors_missing.append("annotation_table")

        # --- assets: one per detail page ---
        for i in detail_idxs:
            m = re.search(r"File name: (\S+)", texts[i])
            assets.append({"kind": "image", "page": i + 1, "ref": m.group(1) if m else None})

    declared = header["declared_counts"]["annotations"]
    return {
        "schema": "rmu.normalized/1",
        "profile": f"{cfg['key']}@{cfg['structural_version']}",
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "header": header,
        "findings": findings,
        "assets": assets,
        "integrity": {
            "anchors_found": anchors_found,
            "anchors_missing": anchors_missing,
            "declared_vs_extracted": {"declared": declared, "extracted": len(findings)},
        },
    }


def is_blocked(normalized: dict) -> tuple[bool, str]:
    """FR-016 integrity gate: anchors missing OR declared != extracted -> BLOCK."""
    integ = normalized["integrity"]
    if integ["anchors_missing"]:
        return True, f"extraction anchors missing: {', '.join(integ['anchors_missing'])}"
    dve = integ["declared_vs_extracted"]
    if dve["declared"] != dve["extracted"]:
        return True, (
            f"declared totals mismatch: document declares {dve['declared']} annotations, "
            f"extracted {dve['extracted']} (suspected drift / silent under-extraction)"
        )
    return False, ""
