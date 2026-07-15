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
        if nonempty and sum(bool(_NUMBERISH.match(v)) for v in nonempty) >= max(1, len(nonempty) // 2):
            number_column = j
            text_column = j + 1
            break
    header_rows = [0]  # single header row for the deterministic floor
    return header_rows, number_column, text_column


def reconstruct_matrix(pdf_path: Path) -> list[dict] | None:
    elements: list[dict] = []
    found_grid = False
    used: dict[str, int] = {}

    def uid(base: str) -> str:
        base = base or "x"
        used[base] = used.get(base, 0) + 1
        return base if used[base] == 1 else f"{base}_{used[base]}"

    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            height = float(page.height)
            for table in page.find_tables():
                grid = table.extract()
                if not grid or len(grid) < 2 or max(len(r) for r in grid) < 3:
                    continue
                found_grid = True
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
                counter = 0
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
                            f"cell-p{page_no}-{counter}", "overlay_region", 0.6,
                            {"pages": [page_no], "source": "heuristic",
                             "row": i, "col": j},
                            {"row_id": rid, "col_id": cid,
                             "target_field": derive_field(rid, cid), "kind": "text",
                             "page": page_no,
                             "bbox": [round(x0, 1), round(height - bottom, 1),
                                      round(x1, 1), round(height - top, 1)]}))
                        counter += 1
    return elements if found_grid else None
