"""Deterministic axis reconstruction for grid targets (feature 005).

pdfplumber's find_tables already yields cell text + exact bbox + (i,j). We keep
that geometry verbatim and add SEMANTIC structure: identify the tower header
band (top rows) and the criterion label band (left columns, number+text), emit
row_axis / col_axis elements, and make every blank answer cell reference both by
(row_id, col_id). No AI here — this is the --no-ai floor. Names are best-effort;
the interpret stage (interpret_matrix.py) and human review improve them.
"""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from rmu.onboard.analyze_target import _element, _slug

GRID_MIN_CELL_W = 12.0
GRID_MIN_CELL_H = 8.0
_NUMBERISH = re.compile(r"^\s*\d+(\.\d+)*\s*$")


def derive_field(row_id: str, col_id: str) -> str:
    return f"{row_id}__{col_id}"


def _text(grid, i, j) -> str:
    try:
        return " ".join((grid[i][j] or "").split())
    except (IndexError, TypeError):
        return ""


def _detect_bands(grid) -> tuple[list[int], int | None, int]:
    """(header_rows, number_column, text_column). Header band = leading rows
    whose left cells are non-numeric labels; number column = a left column whose
    data cells are numeric; text column = the next labelled left column."""
    ncols = max((len(r) for r in grid), default=0)
    # number column: first column that is numeric in most content rows
    number_column = None
    text_column = 0
    for j in range(min(ncols, 3)):
        vals = [_text(grid, i, j) for i in range(1, len(grid))]
        nonempty = [v for v in vals if v]
        numeric = sum(bool(_NUMBERISH.match(v)) for v in nonempty)
        if nonempty and numeric >= max(1, len(nonempty) // 2):
            number_column = j
            text_column = j + 1
            break
    header_rows = [0]  # single header row for the deterministic floor
    return header_rows, number_column, text_column


def _flat_cell_elements(table, grid, page_no: int, height: float,
                        used_fields: dict[str, int], start: int) -> list[dict]:
    """Flat per-cell regions for a table too small to reconstruct as a matrix
    (<2 rows or <3 cols): every blank, size-valid cell still becomes a
    reviewable overlay_region, named nearest-left row label, else column
    header above, else position — mirroring the pre-matrix grid path. Tables
    must never silently lose fillable cells (hard rule: exceptions reported,
    never absorbed)."""
    elements: list[dict] = []
    counter = start
    for i, row in enumerate(table.rows):
        for j, cell in enumerate(row.cells):
            if cell is None:  # merged/absent cell
                continue
            x0, top, x1, bottom = cell
            if x1 - x0 < GRID_MIN_CELL_W or bottom - top < GRID_MIN_CELL_H:
                continue
            if _text(grid, i, j):
                continue  # pre-printed, not fillable
            label, association = "", "positional"
            for jj in range(j - 1, -1, -1):  # nearest left in row
                if _text(grid, i, jj):
                    label, association = _text(grid, i, jj), "row_label"
                    break
            if not label:
                for ii in range(i - 1, -1, -1):  # nearest above in col
                    if _text(grid, ii, j):
                        label, association = _text(grid, ii, j), "col_header"
                        break
            label = label[:60]
            slug = _slug(label)
            if not slug:  # no context anywhere (or non-text glyphs)
                slug = f"cell_p{page_no}_r{i}_c{j}"
                label, association = slug, "positional"
            used_fields[slug] = used_fields.get(slug, 0) + 1
            if used_fields[slug] > 1:
                slug = f"{slug}_{used_fields[slug]}"
            elements.append(_element(
                f"cell-p{page_no}-{counter}", "overlay_region", 0.6,
                {"pages": [page_no], "source": "heuristic",
                 "association": association, "row": i, "col": j},
                {"label": label,
                 "target_field": slug,
                 "kind": "text",
                 "page": page_no,
                 "bbox": [round(x0, 1), round(height - bottom, 1),
                          round(x1, 1), round(height - top, 1)]}))
            counter += 1
    return elements


def reconstruct_matrix(pdf_path: Path) -> list[dict] | None:
    elements: list[dict] = []
    found_grid = False
    used: dict[str, int] = {}
    used_fields: dict[str, int] = {}

    def uid(base: str) -> str:
        base = base or "x"
        used[base] = used.get(base, 0) + 1
        return base if used[base] == 1 else f"{base}_{used[base]}"

    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            height = float(page.height)
            cell_counter = 0  # per-page, continuous across tables (unique ids)
            for table in page.find_tables():
                grid = table.extract()
                if not grid:
                    continue
                found_grid = True
                if len(grid) < 2 or max(len(r) for r in grid) < 3:
                    # too small for axis reconstruction: keep its cells flat
                    # rather than dropping them (never silently absorbed)
                    flat = _flat_cell_elements(
                        table, grid, page_no, height, used_fields, cell_counter)
                    elements.extend(flat)
                    cell_counter += len(flat)
                    continue
                header_rows, number_col, text_col = _detect_bands(grid)
                label_cols = {c for c in (number_col, text_col) if c is not None}

                # row axis (criteria)
                row_entries, row_id_by_i = [], {}
                for i in range(len(grid)):
                    if i in header_rows:
                        continue
                    number = _text(grid, i, number_col) if number_col is not None else None
                    label = _text(grid, i, text_col) or number or f"row_{i}"
                    rid = uid(_slug(label) or f"row_{i}")
                    row_id_by_i[i] = rid
                    row_entries.append({"row": i, "id": rid,
                                        "number": number or None, "label": label[:80]})

                # col axis (towers)
                col_entries, col_id_by_j = [], {}
                ncols = max(len(r) for r in grid)
                for j in range(ncols):
                    if j in label_cols:
                        continue
                    label = _text(grid, header_rows[0], j) or f"col_{j}"
                    cid = uid(_slug(label) or f"col_{j}")
                    col_id_by_j[j] = cid
                    col_entries.append({"col": j, "id": cid, "label": label[:60]})

                elements.append(_element(
                    f"rowaxis-p{page_no}", "row_axis", 0.6,
                    {"pages": [page_no], "source": "heuristic"},
                    {"number_column": number_col, "text_column": text_col,
                     "header_rows": header_rows, "entries": row_entries}))
                elements.append(_element(
                    f"colaxis-p{page_no}", "col_axis", 0.6,
                    {"pages": [page_no], "source": "heuristic"},
                    {"entries": col_entries}))

                # cells (blank answer slots at criterion x tower intersections)
                row_label_by_i = {e["row"]: e["label"] for e in row_entries}
                col_label_by_j = {e["col"]: e["label"] for e in col_entries}
                for i, row in enumerate(table.rows):
                    for j, cell in enumerate(row.cells):
                        if cell is None or i not in row_id_by_i or j not in col_id_by_j:
                            continue
                        x0, top, x1, bottom = cell
                        if x1 - x0 < GRID_MIN_CELL_W or bottom - top < GRID_MIN_CELL_H:
                            continue
                        if _text(grid, i, j):
                            continue  # pre-printed, not fillable
                        rid, cid = row_id_by_i[i], col_id_by_j[j]
                        elements.append(_element(
                            f"cell-p{page_no}-{cell_counter}", "overlay_region", 0.6,
                            {"pages": [page_no], "source": "heuristic",
                             "row": i, "col": j},
                            {"row_id": rid, "col_id": cid,
                             # human-readable name for review sheets and the
                             # pdf_template regions contract (approve/verify)
                             "label": f"{row_label_by_i[i]} × {col_label_by_j[j]}",
                             "target_field": derive_field(rid, cid), "kind": "text",
                             "page": page_no,
                             "bbox": [round(x0, 1), round(height - bottom, 1),
                                      round(x1, 1), round(height - top, 1)]}))
                        cell_counter += 1
    return elements if found_grid else None
