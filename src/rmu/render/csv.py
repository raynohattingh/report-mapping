"""Deterministic CSV rendering: LF newlines, UTF-8 without BOM, stable column
order, minimal quoting. No timestamps anywhere (FR-011, research R1)."""

from __future__ import annotations

import csv
import io


def render_csv(rows: list[dict], columns: list[str]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=columns, extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    return buffer.getvalue().encode("utf-8")
