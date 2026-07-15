"""Seed a deterministic criteria x tower matrix PDF (lines-only grid, blank
answer cells) — the synthetic stand-in for the Eskom Annexure holdout."""
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

OUT = Path(__file__).with_name("matrix_target.pdf")
HEADER = ["No", "Criterion", "T1", "T2", "T3"]
ROWS = [("4.1", "Broken stay wire"), ("4.2", "Corrosion"), ("4.3", "Bird streamer")]
COL_X = [40, 90, 300, 380, 460, 540]   # 5 columns -> 6 boundaries
ROW_Y = [540, 500, 460, 420, 380]      # header + 3 rows -> 5 boundaries (top→down)


def build(out: Path = OUT) -> Path:
    c = canvas.Canvas(str(out), pagesize=landscape(A4))
    for x in COL_X:                                  # vertical grid lines
        c.line(x, ROW_Y[-1], x, ROW_Y[0])
    for y in ROW_Y:                                  # horizontal grid lines
        c.line(COL_X[0], y, COL_X[-1], y)
    for j, label in enumerate(HEADER):               # header text
        c.drawString(COL_X[j] + 3, ROW_Y[0] - 20 + 6, label)
    for i, (num, crit) in enumerate(ROWS):           # number + criterion text
        y = ROW_Y[i + 1] - 20 + 6
        c.drawString(COL_X[0] + 3, y, num)
        c.drawString(COL_X[1] + 3, y, crit)
    # tower columns (j = 2,3,4) left BLANK — the fillable answer cells
    c.showPage()
    c.save()
    return out


if __name__ == "__main__":
    print(build())
