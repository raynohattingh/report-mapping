from pathlib import Path
from rmu.onboard.matrix import reconstruct_matrix, derive_field

FIXTURE = Path("tests/fixtures/onboarding/matrix_target.pdf")

def _by_kind(elements, kind):
    return [e for e in elements if e["element_kind"] == kind]

def test_reconstruct_builds_two_axes_and_cells():
    elements = reconstruct_matrix(FIXTURE)
    assert elements is not None
    row_axis = _by_kind(elements, "row_axis")[0]["payload"]
    col_axis = _by_kind(elements, "col_axis")[0]["payload"]
    # 3 criteria rows, 3 tower columns
    assert len(row_axis["entries"]) == 3
    assert len(col_axis["entries"]) == 3
    # number + text columns detected and paired
    assert row_axis["number_column"] == 0 and row_axis["text_column"] == 1
    # cells = 3 criteria x 3 towers = 9, each referencing both axes
    cells = _by_kind(elements, "overlay_region")
    assert len(cells) == 9
    sample = cells[0]["payload"]
    assert sample["target_field"] == derive_field(sample["row_id"], sample["col_id"])
    assert sample["bbox"] and sample["page"] == 1

def test_reconstruct_returns_none_without_a_grid(tmp_path):
    from reportlab.pdfgen import canvas
    p = tmp_path / "blank.pdf"
    c = canvas.Canvas(str(p)); c.drawString(72, 720, "no grid here"); c.showPage(); c.save()
    assert reconstruct_matrix(p) is None
