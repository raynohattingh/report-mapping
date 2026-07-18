from pathlib import Path

from rmu.onboard.analyze_target import analyze

FIXTURE = Path("tests/fixtures/onboarding/matrix_target.pdf")


def test_analyze_uses_matrix_path_for_grid_targets():
    doc = analyze(FIXTURE, kind="fixed_layout")
    kinds = [e["element_kind"] for e in doc["elements"]]
    assert kinds.count("row_axis") == 1
    assert kinds.count("col_axis") == 1
    assert kinds.count("overlay_region") == 9
    # every cell derives its name from the two axes
    cells = [e for e in doc["elements"] if e["element_kind"] == "overlay_region"]
    assert all("__" in e["payload"]["target_field"] for e in cells)
