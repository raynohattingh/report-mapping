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
    assert dropped["unknown_index"] == 0


def test_interpretation_drops_unknown_indices():
    stub = StubAxisInterpreter({
        "row_axis": {
            "entries": [{"row": 99, "label": "Ghost", "confidence": 0.9}]
        },
        "col_axis": {"entries": []},
    })
    doc, dropped = apply_interpretation(_doc(), GRID, stub)
    assert dropped["unknown_index"] == 1
    row_entries = doc["elements"][0]["payload"]["entries"][0]
    assert "suggested_label" not in row_entries


def test_no_interpreter_is_a_noop():
    doc, dropped = apply_interpretation(_doc(), GRID, None)
    assert dropped == {"unknown_index": 0}
    assert "suggested_label" not in doc["elements"][0]["payload"]["entries"][0]
