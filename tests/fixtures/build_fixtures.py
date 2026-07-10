"""Fixture builder (research R7): synthetic same-structure Scopito-style PDFs.

Dev-only (reportlab is a dev dependency; src/rmu never imports it). Generation
is seeded and deterministic; the resulting PDFs are COMMITTED so tests never
regenerate them. Layout mirrors profile scopito.pdf.powerline.v2020's anchors:
header block (stacked labels), severity overview, annotation table, so the
real extractor parses them through the same code path as the real PDFs (A1).

Fixtures:
- batch_20/synthetic_01..17.pdf  - healthy, varied severities/issues/comments
- batch_20/synthetic_18_zero.pdf - zero findings, declared 0 (analysis C1)
- drifted/drifted_header.pdf     - annotation header renamed Id->Ref: fails the
  profile fingerprint -> unknown-profile quarantine (US2 scenario 4)
- drifted/count_mismatch.pdf     - declares 10 annotations, contains 7 rows:
  passes detection, BLOCKED by declared-vs-extracted integrity (FR-016)

Usage: uv run python tests/fixtures/build_fixtures.py
"""

from __future__ import annotations

import random
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

HERE = Path(__file__).parent
WIDTH, HEIGHT = A4

ISSUES = ["Conductor Damage", "Potential Hazard", "Miscellaneous", "Corrosion",
          "Lightning strike"]
COMMENTS = ["burned lead", "clearance issue", "visually inspect", "rust visible",
            "loose clamp", ""]
SEVERITIES = ["1", "2", "3", "4", "5", "?"]

# Annotation table column x-positions (points). Cells are drawn left-aligned at
# these positions; the extractor's midpoint boundaries recover them.
COLS = {"Id": 30, "Severity": 90, "User tags": 150, "Issues": 260,
        "Comments": 380, "Page": 530}


def _header_page(c: canvas.Canvas, name: str, n_annotations: int, declared: int | None,
                 counts: list[int]) -> None:
    declared = n_annotations if declared is None else declared
    c.setFont("Helvetica-Bold", 14)
    c.drawString(30, 800, name)
    c.setFont("Helvetica", 10)
    c.drawString(30, 760, "Report date:")
    c.drawString(30, 745, "Jul 5, 2026")
    c.drawString(150, 760, "Type:")
    c.drawString(150, 745, "Power Line")
    c.drawString(260, 760, "Company:")
    c.drawString(260, 745, "Synthetic Ops")
    c.drawString(30, 700, "Annotations:")
    c.drawString(35, 685, str(declared))
    c.drawString(150, 700, "Report Images:")
    c.drawString(200, 685, str(n_annotations))
    c.drawString(30, 660, "Severity overview")
    c.drawString(30, 645,
                 "Severity 1 Severity 2 Severity 3 Severity 4 Severity 5 POI ( ? )")
    c.drawString(30, 630, " ".join(str(v) for v in counts))
    c.showPage()


def _annotation_page(c: canvas.Canvas, rows: list[dict], id_header: str = "Id") -> None:
    c.setFont("Helvetica-Bold", 12)
    c.drawString(30, 800, "Annotation overview")
    c.setFont("Helvetica", 9)
    y = 780
    c.drawString(COLS["Id"], y, id_header)
    c.drawString(COLS["Severity"], y, "Severity")
    c.drawString(COLS["User tags"], y, "User tags")
    c.drawString(COLS["Issues"], y, "Issues")
    c.drawString(COLS["Comments"], y, "Comments")
    c.drawString(COLS["Page"], y, "Page")
    y -= 20
    for row in rows:
        c.drawString(COLS["Id"], y, row["id"])
        c.drawString(COLS["Severity"], y, row["severity"])
        c.drawString(COLS["User tags"], y, row["tags"])
        c.drawString(COLS["Issues"], y, row["issues"])
        c.drawString(COLS["Comments"], y, row["comments"])
        c.drawString(COLS["Page"], y, str(row["page"]))
        y -= 20
    c.showPage()


def _rows(rng: random.Random, doc_index: int, count: int) -> list[dict]:
    rows = []
    for j in range(count):
        rows.append({
            "id": f"9{doc_index:02d}{j:04d}",
            "severity": rng.choice(SEVERITIES),
            "tags": f"SYN-{doc_index} | RGB",
            "issues": rng.choice(ISSUES),
            "comments": rng.choice(COMMENTS),
            "page": j + 2,
        })
    return rows


def _severity_counts(rows: list[dict]) -> list[int]:
    return [sum(1 for r in rows if r["severity"] == s) for s in ["1", "2", "3", "4", "5"]] + [
        sum(1 for r in rows if r["severity"] == "?")
    ]


def build_report(path: Path, name: str, rows: list[dict], declared: int | None = None,
                 id_header: str = "Id") -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    _header_page(c, name, len(rows), declared, _severity_counts(rows))
    _annotation_page(c, rows, id_header=id_header)
    c.save()


def main() -> None:
    rng = random.Random(20260711)  # fixed seed: regeneration is reproducible
    batch = HERE / "batch_20"
    drifted = HERE / "drifted"
    batch.mkdir(exist_ok=True)
    drifted.mkdir(exist_ok=True)

    for i in range(1, 18):
        rows = _rows(rng, i, rng.randint(3, 12))
        build_report(batch / f"synthetic_{i:02d}.pdf",
                     f"Synthetic powerline demo {i:02d}", rows)

    # Zero-findings report: valid, empty annotation table, declared 0 (C1).
    build_report(batch / "synthetic_18_zero.pdf",
                 "Synthetic powerline demo 18 (no findings)", [])

    # Drift A: renamed Id column -> fingerprint mismatch -> unknown profile.
    rows = _rows(rng, 90, 5)
    build_report(drifted / "drifted_header.pdf",
                 "Synthetic drifted header demo", rows, id_header="Ref")

    # Drift B: declares 10 annotations but contains 7 rows -> integrity BLOCK.
    rows = _rows(rng, 91, 7)
    build_report(drifted / "count_mismatch.pdf",
                 "Synthetic count mismatch demo", rows, declared=10)

    print(f"built {len(list(batch.glob('*.pdf')))} batch + "
          f"{len(list(drifted.glob('*.pdf')))} drifted fixtures")


if __name__ == "__main__":
    main()
