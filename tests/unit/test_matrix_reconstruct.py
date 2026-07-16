from pathlib import Path

from rmu.onboard.matrix import derive_field, reconstruct_matrix

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

def test_non_qualifying_table_still_emits_flat_cells():
    """target_grid.pdf page 1 has a qualifying 4x4 grid AND a blank 2x2 grid
    (too small for axis reconstruction). The 2x2's cells must survive as flat
    positional overlay_regions — no table's cells may silently vanish."""
    elements = reconstruct_matrix(Path("tests/fixtures/onboarding/target_grid.pdf"))
    assert elements is not None
    cells = _by_kind(elements, "overlay_region")
    fields = {e["payload"]["target_field"] for e in cells}
    # matrix cells from the qualifying grid
    assert {"corrosion__result", "paint__notes"} <= fields
    # flat cells from the non-qualifying 2x2 grid, positional names
    assert {"cell_p1_r0_c0", "cell_p1_r0_c1",
            "cell_p1_r1_c0", "cell_p1_r1_c1"} <= fields
    flat = [e for e in cells if "row_id" not in e["payload"]]
    assert len(flat) == 4
    for e in flat:
        assert e["evidence"]["association"] == "positional"
        assert e["payload"]["label"] and len(e["payload"]["bbox"]) == 4


def test_matrix_cells_carry_human_readable_labels():
    """Cell payloads include a 'row x col' label (approve/verify's regions
    contract requires one; review sheets show it)."""
    elements = reconstruct_matrix(FIXTURE)
    cells = _by_kind(elements, "overlay_region")
    assert all(" × " in e["payload"]["label"] for e in cells)
    sample = next(e["payload"] for e in cells
                  if e["payload"]["target_field"] == "corrosion__t2")
    assert sample["label"] == "Corrosion × T2"


def test_reconstruct_returns_none_without_a_grid(tmp_path):
    from reportlab.pdfgen import canvas
    p = tmp_path / "blank.pdf"
    c = canvas.Canvas(str(p))
    c.drawString(72, 720, "no grid here")
    c.showPage()
    c.save()
    assert reconstruct_matrix(p) is None
