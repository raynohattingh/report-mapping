"""Exceptions report writer: exceptions.csv exists for EVERY run, even a clean
one — the batch is never silently "all fine" (FR-013, Constitution V)."""

from __future__ import annotations

from pathlib import Path

from rmu.render.csv import render_csv

COLUMNS = ["document", "record_ref", "kind", "field", "value", "reason", "suggestion"]


def exceptions_rows(per_document: list[tuple[str, list[dict]]]) -> list[dict]:
    rows = []
    for document, exceptions in per_document:
        for exc in exceptions:
            detail = exc.get("detail", {})
            rows.append({
                "document": document,
                "record_ref": exc.get("record_ref") or "",
                "kind": exc["kind"],
                "field": detail.get("field", ""),
                "value": detail.get("value", ""),
                "reason": detail.get("reason", ""),
                "suggestion": detail.get("suggestion", ""),
            })
    return rows


def write_exceptions_report(out_dir: Path, rows: list[dict]) -> Path:
    path = Path(out_dir) / "exceptions.csv"
    path.write_bytes(render_csv(rows, COLUMNS))
    return path
