from rmu.onboard.interpret_matrix import (
    StubAxisInterpreter,
    apply_interpretation,
)


def _doc():
    return {"elements": [
        {
            "element_kind": "row_axis",
            "payload": {
                "number_column": 0,
                "text_column": 1,
                "header_rows": [0],
                "entries": [
                    {"row": 1, "id": "r1", "number": None, "label": "row_1"}
                ],
            },
        },
        {
            "element_kind": "col_axis",
            "payload": {"entries": [{"col": 2, "id": "c2", "label": "col_2"}]},
        },
    ]}


GRID = {1: [["No", "Criterion", "T1"], ["4.2", "", ""]]}


def test_interpretation_annotates_valid_indices():
    stub = StubAxisInterpreter({
        "row_axis": {
            "entries": [
                {
                    "row": 1,
                    "number": "4.2",
                    "label": "Corrosion",
                    "confidence": 0.9,
                }
            ]
        },
        "col_axis": {
            "entries": [{"col": 2, "label": "Tower 100", "confidence": 0.8}]
        },
    })
    doc, dropped = apply_interpretation(_doc(), GRID, stub)
    row = doc["elements"][0]["payload"]["entries"][0]
    col = doc["elements"][1]["payload"]["entries"][0]
    assert row["suggested_label"] == "Corrosion"
    assert row["suggested_number"] == "4.2"
    assert col["suggested_label"] == "Tower 100"
    assert row["label"] == "row_1"  # original NOT overwritten
    assert dropped == {"unknown_index": 0, "unmatched_axis_entry": 0}


def test_interpretation_drops_unknown_indices():
    stub = StubAxisInterpreter({
        "row_axis": {
            "entries": [{"row": 99, "label": "Ghost", "confidence": 0.9}]
        },
        "col_axis": {"entries": []},
    })
    doc, dropped = apply_interpretation(_doc(), GRID, stub)
    assert dropped == {"unknown_index": 1, "unmatched_axis_entry": 0}
    row_entries = doc["elements"][0]["payload"]["entries"][0]
    assert "suggested_label" not in row_entries


def test_interpretation_counts_in_bounds_but_unmatched_entries():
    """A (row, col) that exists in the grid but names no axis entry is
    dropped and counted, never silently absorbed (the 'unmatched, uncounted'
    gap closed in feature 005's final review)."""
    stub = StubAxisInterpreter({
        "row_axis": {
            # row 0 is in-bounds (GRID has rows 0-1) but no axis entry has
            # row == 0 (the only row_axis entry is row 1)
            "entries": [{"row": 0, "label": "Header Row", "confidence": 0.5}]
        },
        "col_axis": {
            # col 0 is in-bounds but no col_axis entry has col == 0
            "entries": [{"col": 0, "label": "No column", "confidence": 0.5}]
        },
    })
    doc, dropped = apply_interpretation(_doc(), GRID, stub)
    assert dropped == {"unknown_index": 0, "unmatched_axis_entry": 2}
    assert "suggested_label" not in doc["elements"][0]["payload"]["entries"][0]
    assert "suggested_label" not in doc["elements"][1]["payload"]["entries"][0]


def test_no_interpreter_is_a_noop():
    doc, dropped = apply_interpretation(_doc(), GRID, None)
    assert dropped == {"unknown_index": 0, "unmatched_axis_entry": 0}
    assert "suggested_label" not in doc["elements"][0]["payload"]["entries"][0]
