"""003 onboarding fixture builder (T004, plan research R3/R7).

Deterministic (fixed seed + reportlab invariant mode); outputs are COMMITTED so
tests never regenerate them. The synthetic source shape ("FieldSurvey") is
deliberately DIFFERENT from profile scopito.pdf.powerline.v2020 — none of that
profile's fingerprint anchors appear — so these PDFs exercise the
unrecognised-source path (FR-001) without colliding with the registered profile.

NEVER reads or imitates the quarantined SC-001 acceptance fixture (see
tests/invariants/test_quarantine.py for the enforced rule).

Fixtures (tests/fixtures/onboarding/):
- survey_report_a.pdf / survey_report_b.pdf  same new shape, different data
- survey_report_drifted.pdf                  'Class' column renamed 'Category'
- survey_report_indented.pdf                 table header indented right of data
- prose_report.pdf                           valid text, no structure (FR-001b)
- target_form.pdf                            AcroForm: text/checkbox/choice, required flags
- target_fixed.pdf                           fixed-layout: labels + blank boxes + photo box
- target_encrypted.pdf                       password-protected (FR-010)
- scanned_only.pdf                           image-only pages, no text layer (FR-010)

Usage: uv run python tests/fixtures/make_fixtures.py
"""

from __future__ import annotations

import io
import random
import struct
import zlib
from pathlib import Path

from pypdf import PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

HERE = Path(__file__).parent
OUT = HERE / "onboarding"
WIDTH, HEIGHT = A4

CLASSES = ["Structural", "Electrical", "Vegetation", "Corrosion"]
COMPONENTS = ["Cross-arm", "Insulator", "Conductor", "Stay wire", "Pole"]
OBSERVATIONS = ["hairline crack", "flashover marks", "encroachment 2m", "rust scaling",
                "broken strand", "leaning 5 deg"]

# Defect register column x-positions (points) — different names AND geometry
# from the scopito fixture so structure detection is genuinely new.
COLS = {"Ref": 40, "Class": 110, "Component": 210, "Observation": 320, "Sheet": 520}


def _png(rgb: tuple[int, int, int], size: int = 24) -> bytes:
    """Minimal deterministic PNG (no timestamps, no ancillary chunks)."""
    row = b"\x00" + bytes(rgb) * size
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(row * size, 9)) + chunk(b"IEND", b""))


def _canvas(path: Path) -> canvas.Canvas:
    # invariant=1: reportlab pins generation metadata -> byte-reproducible output
    return canvas.Canvas(str(path), pagesize=A4, invariant=1)


def _survey_header(c: canvas.Canvas, title: str, n: int) -> None:
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, 800, title)
    c.setFont("Helvetica", 10)
    c.drawString(40, 770, "Survey date: 03 Jul 2026")
    c.drawString(40, 755, "Client: Synthetic Utility Co")
    c.drawString(40, 740, "Site: Feeder 11 North")
    c.drawString(40, 725, f"Defects recorded: {n}")


def _furniture(c: canvas.Canvas, page_no: int) -> None:
    c.setFont("Helvetica", 8)
    c.drawString(40, 812, "FieldSurvey Pro export")          # repeated header line
    c.drawString(40, 28, f"Confidential - page {page_no}")   # repeated footer line


def _register_header(c: canvas.Canvas, y: int, class_col: str, header_dx: int = 0) -> int:
    # header_dx shifts the header words right of the data columns: real exports
    # (e.g. Scopito) indent the table header relative to the data rows, which
    # broke header-anchored column detection (see build_survey_indented).
    c.setFont("Helvetica-Bold", 9)
    for name, x in COLS.items():
        c.drawString(x + header_dx, y, class_col if name == "Class" else name)
    c.setFont("Helvetica", 9)
    return y - 18


def _survey_rows(rng: random.Random, count: int) -> list[dict]:
    return [{
        "ref": f"DF-{i:03d}",
        "cls": rng.choice(CLASSES),
        "component": rng.choice(COMPONENTS),
        "observation": rng.choice(OBSERVATIONS),
        "sheet": i // 2 + 1,
        "rgb": (40 * (i % 6) + 15, 200 - 25 * (i % 7), 90 + 20 * (i % 8)),
    } for i in range(1, count + 1)]


def build_survey(path: Path, title: str, rows: list[dict], class_col: str = "Class") -> None:
    c = _canvas(path)
    page_no = 1
    _furniture(c, page_no)
    _survey_header(c, title, len(rows))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, 690, "Defect register")
    y = _register_header(c, 670, class_col)
    for row in rows:
        if y < 80:  # page break: repeat furniture + table header (continuation case)
            c.showPage()
            page_no += 1
            _furniture(c, page_no)
            y = _register_header(c, 780, class_col)
        c.drawString(COLS["Ref"], y, row["ref"])
        c.drawString(COLS["Class"], y, row["cls"])
        c.drawString(COLS["Component"], y, row["component"])
        c.drawString(COLS["Observation"], y, row["observation"])
        c.drawString(COLS["Sheet"], y, str(row["sheet"]))
        # per-record thumbnail right of the row -> image-region detection (FR-001a)
        img = ImageReader(io.BytesIO(_png(row["rgb"])))
        c.drawImage(img, 560, y - 4, width=16, height=16)
        y -= 26
    c.showPage()
    c.save()


def build_survey_indented(path: Path, title: str, rows: list[dict]) -> None:
    """Regression fixture for two analyze_source pass-2 bugs seen on real
    exports (e.g. Scopito):

    (a) the table header is drawn ~12pt to the RIGHT of the data columns — real
        exports indent the header relative to the data rows, which broke
        header-anchored column-range detection; and
    (b) every 4th row omits its middle cells (sparse row) — the old fill-
        threshold row count then diverges from the deterministic extractor's
        row_pattern count, so recurrence != extraction.
    Single page, no continuation, so both effects are isolated."""
    c = _canvas(path)
    _furniture(c, 1)
    _survey_header(c, title, len(rows))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, 690, "Defect register")
    y = _register_header(c, 670, "Class", header_dx=12)  # header indented right
    for i, row in enumerate(rows, 1):
        c.drawString(COLS["Ref"], y, row["ref"])       # ref + sheet on every row
        c.drawString(COLS["Sheet"], y, str(row["sheet"]))
        if i % 4 != 0:                                  # every 4th row is sparse
            c.drawString(COLS["Class"], y, row["cls"])
            c.drawString(COLS["Component"], y, row["component"])
            c.drawString(COLS["Observation"], y, row["observation"])
        img = ImageReader(io.BytesIO(_png(row["rgb"])))
        c.drawImage(img, 560, y - 4, width=16, height=16)
        y -= 26
    c.showPage()
    c.save()


def build_prose(path: Path) -> None:
    c = _canvas(path)
    _furniture(c, 1)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, 790, "Quarterly network condition narrative")
    c.setFont("Helvetica", 10)
    text = c.beginText(40, 760)
    for line in [
        "This narrative summarises the general condition of the network as observed",
        "during routine patrols. No tabulated defect register accompanies this",
        "document; findings are described qualitatively in the paragraphs below.",
        "", "Vegetation pressure remains the dominant theme in the northern feeders,",
        "with several spans approaching statutory clearance limits. Hardware",
        "condition is broadly acceptable although isolated corrosion was noted.",
    ]:
        text.textLine(line)
    c.drawText(text)
    c.showPage()
    c.save()


def build_form(path: Path) -> None:
    c = _canvas(path)
    form = c.acroForm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, 800, "Defect Notification Form (synthetic)")
    c.setFont("Helvetica", 10)
    c.drawString(40, 760, "Asset ID:")
    form.textfield(name="asset_id", x=150, y=750, width=200, height=18,
                   fieldFlags="required", borderWidth=0.5)
    c.drawString(40, 720, "Defect code:")
    form.textfield(name="defect_code", x=150, y=710, width=120, height=18,
                   fieldFlags="required", maxlen=6, borderWidth=0.5)
    c.drawString(40, 680, "Priority:")
    form.choice(name="priority", x=150, y=670, width=90, height=18,
                options=[("P1", "P1"), ("P2", "P2"), ("P3", "P3"), ("P4", "P4")],
                value="P4", fieldFlags="combo required")
    c.drawString(40, 640, "Comments:")
    form.textfield(name="comments", x=150, y=600, width=380, height=50,
                   fieldFlags="multiline", borderWidth=0.5)
    c.drawString(40, 560, "Re-inspection required:")
    form.checkbox(name="reinspect", x=200, y=555, size=14)
    c.showPage()
    c.save()


def build_fixed(path: Path) -> None:
    c = _canvas(path)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, 800, "Defect Record Sheet (synthetic fixed layout)")
    c.setFont("Helvetica", 10)
    for label, y in [("Asset ID:", 750), ("Defect code:", 710), ("Priority:", 670),
                     ("Observation:", 630), ("Inspection date:", 590)]:
        c.drawString(40, y, label)
        c.rect(150, y - 4, 220, 16)          # blank value box right of the label
    c.drawString(400, 750, "Photo:")
    c.rect(400, 600, 150, 140)               # photo box (image region)
    c.showPage()
    c.save()


def build_encrypted(path: Path) -> None:
    plain = io.BytesIO()
    c = canvas.Canvas(plain, pagesize=A4, invariant=1)
    c.drawString(40, 800, "Locked target document")
    c.showPage()
    c.save()
    plain.seek(0)
    writer = PdfWriter(clone_from=plain)
    writer.encrypt("owner-secret")
    with path.open("wb") as fh:
        writer.write(fh)


def build_scanned(path: Path) -> None:
    c = _canvas(path)
    for rgb in [(200, 200, 190), (190, 195, 200)]:
        img = ImageReader(io.BytesIO(_png(rgb, size=64)))
        c.drawImage(img, 0, 0, width=WIDTH, height=HEIGHT)  # full-page image, no text
        c.showPage()
    c.save()


def main() -> None:
    rng = random.Random(20260712)  # fixed seed
    OUT.mkdir(exist_ok=True)
    build_survey(OUT / "survey_report_a.pdf", "Feeder 11 North - Defect Survey",
                 _survey_rows(rng, 26))  # 26 rows -> spans a page break (continuation case)
    build_survey(OUT / "survey_report_b.pdf", "Feeder 12 East - Defect Survey",
                 _survey_rows(rng, 9))
    build_survey(OUT / "survey_report_drifted.pdf", "Feeder 13 South - Defect Survey",
                 _survey_rows(rng, 7), class_col="Category")
    build_prose(OUT / "prose_report.pdf")
    # Own RNG + built after the shared-rng reports so their committed bytes are
    # unchanged; header indented right of the data columns (see build function).
    irng = random.Random(20260713)
    build_survey_indented(OUT / "survey_report_indented.pdf",
                          "Feeder 14 West - Defect Survey", _survey_rows(irng, 12))
    build_form(OUT / "target_form.pdf")
    build_fixed(OUT / "target_fixed.pdf")
    build_encrypted(OUT / "target_encrypted.pdf")
    build_scanned(OUT / "scanned_only.pdf")
    print(f"built {len(list(OUT.glob('*.pdf')))} onboarding fixtures in {OUT}")


if __name__ == "__main__":
    main()
