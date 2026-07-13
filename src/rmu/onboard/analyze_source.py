"""Structural analysis of an unrecognised source PDF -> draft profile proposal
document (feature 003, research R3, FR-001/FR-001a/FR-002/FR-024).

Three deterministic passes over pdfplumber geometry:
1. page anatomy   - recurring lines across pages -> furniture, excluded below
2. record shape   - a header line above >=3 aligned same-signature rows -> the
                    record table, its columns, and their x-ranges
3. header fields  - 'Label: value' lines on early pages -> key/value candidates

Confidence is structural evidence ONLY (recurrence, alignment, cross-exemplar
agreement) — never name similarity (Constitution V). With extra exemplars the
proposal is cross-checked: elements that fail to generalise are down-scored
and flagged `non_generalising` (FR-001). AI never proposes structure; optional
naming enrichment happens separately (enrich.py, FR-020).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pdfplumber

from rmu.extract.pdf_lines import page_lines

#: pages considered for header fields / fingerprint anchors
LEAD_PAGES = 4
#: minimum aligned data rows under a header line to call it a record table
MIN_RECORD_ROWS = 3
#: fraction of pages a line must recur on to count as furniture
FURNITURE_PAGE_FRACTION = 0.6
#: cross-exemplar down-score factor for non-generalising elements
DISAGREEMENT_FACTOR = 0.5

_LABEL_RE = re.compile(r"^([A-Z][A-Za-z ]{1,30}:)\s*(.*)$")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _column_signature(words: list[dict]) -> tuple[int, ...]:
    return tuple(round(w["x0"] / 12) for w in words)


def _first_cell_pattern(cells: list[str]) -> str:
    """Derive a row-identity regex from observed first-column values by
    structure class (letters/digits), e.g. 'DF-001' -> ^DF-\\d{3}$."""

    def classify(value: str) -> str:
        return re.sub(r"\d+", lambda m: rf"\d{{{len(m.group())}}}", re.escape(value))

    patterns = {classify(c) for c in cells if c}
    if len(patterns) == 1:
        return f"^{patterns.pop()}$"
    # fall back to the loosest common shape: anything non-empty, reviewed by the human
    return r"^\S+$"


def _analyze_one(pdf_path: Path) -> dict:
    """Single-exemplar pass -> {furniture, table, header_fields, images, page_count}."""
    with pdfplumber.open(pdf_path) as pdf:
        pages = list(pdf.pages)
        lines_by_page = [page_lines(p) for p in pages]
        images_by_page = [
            [{"top": i["top"], "bottom": i["bottom"], "x0": i["x0"]} for i in p.images]
            for p in pages
        ]

    # -- pass 1: furniture (recurring identical-prefix lines across pages) ----
    furniture: list[str] = []
    if len(pages) > 1:
        counts: dict[str, int] = {}
        for lines in lines_by_page:
            for text in {line["text"] for line in lines}:
                # normalize trailing numbers (page counters) to a prefix
                prefix = re.sub(r"\d+$", "", text).strip()
                counts[prefix] = counts.get(prefix, 0) + 1
        furniture = sorted(
            prefix
            for prefix, n in counts.items()
            if len(prefix) >= 8 and n / len(pages) >= FURNITURE_PAGE_FRACTION
        )

    def is_furniture(text: str) -> bool:
        return any(text.startswith(f) for f in furniture)

    # -- pass 2: record table --------------------------------------------------
    # A real record table is a header line of >=4 column words above >=3 rows
    # whose FIRST CELL shares one structure class (letters verbatim, digit runs
    # abstracted): 'DF-001'/'DF-002' agree; 'This'/'during' (prose) and
    # 'Survey'/'Client:' (header block) do not. That structural dominance —
    # not any name similarity — is what qualifies a candidate (Constitution V).
    def _class_of(cell: str) -> str:
        return re.sub(r"\d+", lambda m: rf"\d{{{len(m.group())}}}", re.escape(cell))

    best_table: dict | None = None
    for page_idx, lines in enumerate(lines_by_page):
        for i, line in enumerate(lines):
            words = line["words"]
            # NB: a table header that repeats on every page (continuation) looks
            # like furniture — furniture must not veto header candidacy.
            if len(words) < 4:
                continue
            starts = [w["x0"] for w in words]
            ends = starts[1:] + [starts[-1] + 60]
            x_ranges = [[round(s - 4, 1), round(e - 4, 1)] for s, e in zip(starts, ends)]

            def _candidate_rows(candidates: list[dict], header_text: str) -> list[dict]:
                picked = []
                for data in candidates:
                    if is_furniture(data["text"]) or data["text"] == header_text:
                        continue
                    from rmu.extract.pdf_lines import assign_columns

                    cells = assign_columns(data["words"], x_ranges)
                    filled = sum(1 for c in cells if c)
                    if cells and cells[0] and filled >= max(3, len(x_ranges) - 2):
                        picked.append({"line": data, "first_cell": cells[0]})
                return picked

            rows = _candidate_rows(lines[i + 1:], line["text"])
            if len(rows) < MIN_RECORD_ROWS:
                continue
            # dominant first-cell structure class must own >=75% of the rows
            classes: dict[str, int] = {}
            for r in rows:
                cls = _class_of(r["first_cell"])
                classes[cls] = classes.get(cls, 0) + 1
            dominant_class, dominant_n = max(classes.items(), key=lambda kv: kv[1])
            if dominant_n < MIN_RECORD_ROWS or dominant_n / len(rows) < 0.75:
                continue
            rows = [r for r in rows if _class_of(r["first_cell"]) == dominant_class]
            # continuation rows on later pages (repeated header excluded above)
            for later in lines_by_page[page_idx + 1:]:
                rows += [
                    r
                    for r in _candidate_rows(later, line["text"])
                    if _class_of(r["first_cell"]) == dominant_class
                ]
            candidate = {
                "header_line": line,
                "columns": [w["text"] for w in words],
                "x_ranges": x_ranges,
                "rows": [{"top": r["line"]["top"], "words": r["line"]["words"],
                          "first_cell": r["first_cell"]} for r in rows],
                "page": page_idx + 1,
            }
            if best_table is None or len(rows) > len(best_table["rows"]):
                best_table = candidate
        if best_table:
            break  # first page with a table wins; later pages are continuation

    # a repeating table header is continuation anatomy, not furniture
    if best_table:
        header_prefix = re.sub(r"\d+$", "", best_table["header_line"]["text"]).strip()
        furniture = [f for f in furniture if f != header_prefix]

    # -- pass 3: header key/value fields on lead pages, above the table -------
    header_fields: list[dict] = []
    table_top = (
        best_table["header_line"]["top"] if best_table else float("inf")
    )
    for page_idx, lines in enumerate(lines_by_page[:LEAD_PAGES]):
        for line in lines:
            if is_furniture(line["text"]):
                continue
            if page_idx + 1 == (best_table["page"] if best_table else -1) and (
                line["top"] >= table_top
            ):
                continue
            m = _LABEL_RE.match(line["text"])
            if m and m.group(2):
                header_fields.append(
                    {"label": m.group(1), "value": m.group(2), "page": page_idx + 1}
                )

    # -- images correlated to record rows (FR-001a) -----------------------------
    image_hits, orphans = 0, 0
    if best_table:
        row_tops = {round(r["top"]) for r in best_table["rows"]}
        for images in images_by_page:
            for img in images:
                if any(img["top"] - 14 <= t <= img["bottom"] + 14 for t in row_tops):
                    image_hits += 1
                else:
                    orphans += 1

    return {
        "sha": _sha(pdf_path),
        "page_count": len(pages),
        "furniture": furniture,
        "table": best_table,
        "header_fields": header_fields,
        "image_hits": image_hits,
        "image_orphans": orphans,
        "lead_text": "\n".join(
            line["text"] for lines in lines_by_page[:LEAD_PAGES] for line in lines
        ),
    }


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


def analyze(
    exemplars: list[Path],
    *,
    seed_profile: dict | None = None,
) -> dict:
    """Exemplar PDF(s) -> draft profile proposal document (proposal.schema.json).

    Extra exemplars cross-check the primary's proposal; the analysis itself is
    pure heuristics — enrichment (naming hints) is layered on separately."""
    results = [_analyze_one(Path(p)) for p in exemplars]
    primary, extras = results[0], results[1:]
    elements: list[dict] = []

    # furniture
    for i, text in enumerate(primary["furniture"]):
        agreement = _agreement(extras, lambda r, t=text: t in r["furniture"])
        elements.append(
            _element(
                f"furn-{i}", "furniture_line",
                0.5 + 0.4 * (primary["page_count"] > 1) * agreement,
                {"pages": list(range(1, primary["page_count"] + 1)),
                 "recurrence": primary["page_count"],
                 "cross_exemplar_agreement": agreement, "source": "heuristic"},
                {"text": text},
                flags=None if agreement == 1.0 else ["non_generalising"],
            )
        )

    # record table + columns
    table = primary["table"]
    if table:
        rows_n = len(table["rows"])
        table_conf = min(0.95, rows_n / (rows_n + 2))
        agreement = _agreement(extras, lambda r: bool(r["table"]))
        first_cells = [r["first_cell"] for r in table["rows"][:20]]
        elements.append(
            _element(
                "table-0", "record_table",
                table_conf * (1.0 if agreement == 1.0 else DISAGREEMENT_FACTOR),
                {"pages": [table["page"]], "recurrence": rows_n,
                 "cross_exemplar_agreement": agreement, "source": "heuristic"},
                {"detection": {
                    "mode": "column_clusters",
                    "column_x_ranges": table["x_ranges"],
                    "row_pattern": _first_cell_pattern(first_cells),
                    "table_header_regex": "^" + r"\s+".join(
                        re.escape(c) for c in table["columns"]
                    ) + "$",
                }, "continuation": {"mode": "repeat_header"}},
                flags=None if agreement == 1.0 else ["non_generalising"],
            )
        )
        for ci, name in enumerate(table["columns"]):
            col_agreement = _agreement(
                extras,
                lambda r, n=name: bool(r["table"]) and n in r["table"]["columns"],
            )
            conf = table_conf * (
                1.0 if col_agreement == 1.0 else DISAGREEMENT_FACTOR
            )
            elements.append(
                _element(
                    f"col-{ci}", "record_column", conf,
                    {"pages": [table["page"]], "recurrence": rows_n,
                     "cross_exemplar_agreement": col_agreement, "source": "heuristic"},
                    {"name": _slug(name), "source_header": name},
                    flags=None if col_agreement == 1.0 else ["non_generalising"],
                )
            )

    # header fields
    for hi, hf in enumerate(primary["header_fields"]):
        agreement = _agreement(
            extras,
            lambda r, lbl=hf["label"]: any(o["label"] == lbl for o in r["header_fields"]),
        )
        elements.append(
            _element(
                f"hdr-{hi}", "header_field",
                (0.6 + (0.2 if hf["value"] else 0.0))
                * (1.0 if agreement == 1.0 else DISAGREEMENT_FACTOR),
                {"pages": [hf["page"]], "recurrence": 1,
                 "cross_exemplar_agreement": agreement, "source": "heuristic"},
                {"name": _slug(hf["label"]), "strategy": "label_right",
                 "labels": [hf["label"]], "example_value": hf["value"]},
                flags=None if agreement == 1.0 else ["non_generalising"],
            )
        )

    # image regions
    if primary["image_hits"]:
        flags = ["orphan_image"] if primary["image_orphans"] else None
        elements.append(
            _element(
                "img-0", "image_region",
                min(0.9, primary["image_hits"] / (primary["image_hits"] + 2)),
                {"pages": [table["page"]] if table else [1],
                 "recurrence": primary["image_hits"], "source": "heuristic"},
                {"name": "photo", "association": "row_y_overlap"},
                flags=flags,
            )
        )

    # fingerprint anchors (FR-024): distinctive static lead texts + table header
    anchors = [hf["label"] for hf in primary["header_fields"][:2]]
    if table:
        header_text = table["header_line"]["text"]
        # the line ABOVE the table header often names the register/table
        anchors.append(header_text)
    for ai, anchor in enumerate(a for a in anchors if a):
        agreement = _agreement(extras, lambda r, a=anchor: a in r["lead_text"])
        elements.append(
            _element(
                f"fp-{ai}", "fingerprint_anchor",
                0.7 * (1.0 if agreement == 1.0 else DISAGREEMENT_FACTOR),
                {"pages": [1], "recurrence": 1,
                 "cross_exemplar_agreement": agreement, "source": "heuristic"},
                {"required_text": anchor},
                flags=None if agreement == 1.0 else ["non_generalising"],
            )
        )

    if seed_profile and seed_profile.get("recipe"):
        _annotate_seed_delta(elements, seed_profile["recipe"])

    return {
        "kind": "profile",
        "exemplars": [r["sha"] for r in results],
        **({"seeded_from": seed_profile["ref"]} if seed_profile else {}),
        "elements": elements,
    }


def _annotate_seed_delta(elements: list[dict], seed: dict) -> None:
    """FR-021: a seeded (drift re-onboarding) proposal is reviewed as a DELTA
    against the known shape — elements matching the seeding recipe get
    evidence.seed_match, divergent comparable elements get `seed_divergent`."""
    seed_columns = {c["name"] for c in seed.get("records", {}).get("columns", [])}
    seed_labels = {
        label for f in seed.get("header_fields", []) for label in f.get("labels", [])
    }
    seed_furniture = set(seed.get("furniture", []))
    seed_anchors = set(seed.get("fingerprint", {}).get("required_text", []))
    seed_header_regex = seed.get("records", {}).get("detection", {}).get(
        "table_header_regex"
    )

    def mark(element: dict, matched: bool) -> None:
        element["evidence"] = {**element.get("evidence", {}), "seed_match": matched}
        if not matched:
            element["flags"] = sorted(set(element.get("flags", [])) | {"seed_divergent"})

    for e in elements:
        kind, payload = e["element_kind"], e["payload"]
        if kind == "record_column":
            mark(e, payload["name"] in seed_columns)
        elif kind == "header_field":
            mark(e, bool(set(payload.get("labels", [])) & seed_labels))
        elif kind == "furniture_line":
            mark(e, payload["text"] in seed_furniture)
        elif kind == "fingerprint_anchor":
            mark(e, payload["required_text"] in seed_anchors)
        elif kind == "record_table":
            proposed_regex = payload.get("detection", {}).get("table_header_regex")
            mark(e, bool(seed_header_regex) and proposed_regex == seed_header_regex)


def _agreement(extras: list[dict], predicate) -> float:
    """1.0 when every extra exemplar agrees (or none supplied), else fraction."""
    if not extras:
        return 1.0
    return sum(1 for r in extras if predicate(r)) / len(extras)
