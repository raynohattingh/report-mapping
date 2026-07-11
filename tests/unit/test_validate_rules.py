"""T050: template validation_rules enforced — vocabulary legality from inline
lists and the defect-code CSV (design §4 Validate stage)."""

from rmu.validate.rules import load_vocabularies, validate_rows

RULES = {
    "priority": {"vocabulary": ["P1", "P2", "P3", "P4", "POI"]},
    "defect_code": {"vocabulary_csv": "seed/defect_codes_v1.csv", "code_column": "code"},
}


def test_vocabularies_load_from_inline_and_csv():
    vocabs = load_vocabularies(RULES)
    assert vocabs["priority"] == {"P1", "P2", "P3", "P4", "POI"}
    assert "A1" in vocabs["defect_code"] and "F12" in vocabs["defect_code"]
    assert "ZZZ" not in vocabs["defect_code"]


def test_illegal_value_removes_row_and_reports():
    vocabs = load_vocabularies(RULES)
    rows = [
        {"finding_id": "1", "priority": "P1", "defect_code": "C1"},
        {"finding_id": "2", "priority": "P9", "defect_code": "C1"},   # bad priority
        {"finding_id": "3", "priority": "P2", "defect_code": "ZZZ"},  # bad code
    ]
    valid, problems = validate_rows(rows, vocabs)
    assert [r["finding_id"] for r in valid] == ["1"]
    assert {(p["record_ref"], p["kind"]) for p in problems} == {
        ("2", "invalid_value"), ("3", "invalid_value"),
    }
    reasons = {p["record_ref"]: p["detail"] for p in problems}
    assert reasons["2"]["field"] == "priority" and "'P9'" in reasons["2"]["reason"]
    assert reasons["3"]["field"] == "defect_code"
    assert all(p["detail"]["suggestion"] for p in problems)


def test_fields_absent_from_rules_pass_through():
    valid, problems = validate_rows(
        [{"finding_id": "1", "comments": "anything at all"}], load_vocabularies(RULES)
    )
    assert len(valid) == 1 and problems == []
