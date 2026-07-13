"""T011 — structural analysis heuristics (research R3, FR-001/FR-001a/FR-002/FR-024).

Confidence must come from structural evidence (recurrence, alignment,
cross-exemplar agreement) — never from field-name overlap (Constitution V)."""

from __future__ import annotations

from pathlib import Path

from rmu.onboard.analyze_source import analyze

FIX = Path("tests/fixtures/onboarding")


def _by_kind(doc: dict, kind: str) -> list[dict]:
    return [e for e in doc["elements"] if e["element_kind"] == kind]


def test_single_exemplar_proposes_full_recipe_elements():
    doc = analyze([FIX / "survey_report_a.pdf"])
    assert doc["kind"] == "profile"
    assert len(doc["exemplars"]) == 1 and len(doc["exemplars"][0]) == 64

    names = {c["payload"]["name"] for c in _by_kind(doc, "record_column")}
    assert {"ref", "class", "component", "observation", "sheet"} <= names

    tables = _by_kind(doc, "record_table")
    assert len(tables) == 1
    assert tables[0]["payload"]["detection"]["mode"] == "column_clusters"

    labels = {label for h in _by_kind(doc, "header_field") for label in h["payload"]["labels"]}
    assert "Survey date:" in labels and "Client:" in labels

    assert _by_kind(doc, "fingerprint_anchor")  # FR-024: reviewable fingerprint
    assert _by_kind(doc, "image_region")  # FR-001a

    for e in doc["elements"]:
        assert 0.0 <= e["confidence"] <= 1.0
        assert e["evidence"]["source"] == "heuristic"
        assert e["review_state"] == "proposed"


def test_furniture_excluded_from_records_and_headers():
    doc = analyze([FIX / "survey_report_a.pdf"])
    furniture = {f["payload"]["text"] for f in _by_kind(doc, "furniture_line")}
    assert any("FieldSurvey Pro export" in t for t in furniture)
    header_names = {h["payload"]["name"] for h in _by_kind(doc, "header_field")}
    assert not any("confidential" in n for n in header_names)


def test_record_rows_detected_across_page_break():
    doc = analyze([FIX / "survey_report_a.pdf"])
    table = _by_kind(doc, "record_table")[0]
    assert table["evidence"]["recurrence"] >= 26  # rows on page 1 AND page 2


def test_cross_exemplar_agreement_vs_mismatch(tmp_path):
    same = analyze([FIX / "survey_report_a.pdf", FIX / "survey_report_b.pdf"])
    drift = analyze([FIX / "survey_report_a.pdf", FIX / "survey_report_drifted.pdf"])

    def column(doc: dict, name: str) -> dict:
        return next(c for c in _by_kind(doc, "record_column") if c["payload"]["name"] == name)

    agreeing = column(same, "class")
    assert "non_generalising" not in agreeing.get("flags", [])

    disagreeing = column(drift, "class")  # drifted exemplar renames Class->Category
    assert "non_generalising" in disagreeing.get("flags", [])
    assert disagreeing["confidence"] < agreeing["confidence"]  # FR-001 down-scoring


def test_prose_pdf_yields_no_structure():
    doc = analyze([FIX / "prose_report.pdf"])
    assert _by_kind(doc, "record_table") == []
    assert _by_kind(doc, "record_column") == []


def test_indented_header_detected():
    """Regression: a table header indented right of the data rows must still be
    recognised as the header — not fall back to the first data row (the bug that
    broke onboarding the Scopito exports)."""
    doc = analyze([FIX / "survey_report_indented.pdf"])
    tables = _by_kind(doc, "record_table")
    assert len(tables) == 1

    # columns are the REAL header names, not data values like 'DF-001'
    names = [c["payload"]["name"] for c in _by_kind(doc, "record_column")]
    assert names == ["ref", "class", "component", "observation", "sheet"]

    det = tables[0]["payload"]["detection"]
    assert det["row_pattern"] == r"^DF\-\d{3}$"  # re.escape'd hyphen
    assert det["table_header_regex"] == r"^Ref\s+Class\s+Component\s+Observation\s+Sheet$"


def test_recurrence_matches_extraction(tmp_path, monkeypatch):
    """The analyzer's row count (evidence.recurrence) must equal what the
    deterministic extractor produces, so approve-time row_count_exact is a
    genuine determinism guard — even when sparse rows would be dropped by the
    detection fill-threshold."""
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    from rmu.extract.recipe_pdf import extract
    from rmu.onboard.approve import recipe_from_elements

    exemplar = FIX / "survey_report_indented.pdf"
    doc = analyze([exemplar])
    for e in doc["elements"]:
        e["review_state"] = "confirmed"
    recipe = recipe_from_elements(doc, "synthetic.pdf.indented", "v1")

    table = _by_kind(doc, "record_table")[0]
    n = extract(exemplar, recipe)
    assert len(n["findings"]) == table["evidence"]["recurrence"] == 12
