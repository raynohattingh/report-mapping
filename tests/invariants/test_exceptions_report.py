"""T029 [TDD] — never cut (D3): OOV values become exceptions, never guesses
(FR-012); parse-error records become per-record exceptions while the document
still converts (FR-016 record rule); every run emits an exceptions report,
even a clean one (FR-013)."""

import yaml

from rmu.apply.records import apply_records

DOC = yaml.safe_load("""
meta: {source_profile: scopito.pdf.powerline@v2020, target_template: interim.defect_csv@1, version: 1}
routes:
  finding_id: {from: finding.id, tier: T0}
  priority:
    from: finding.severity
    tier: T1
    value_map: {name: severity_to_priority, version: 1}
constants: {inspection_method: UAV visual}
""")

VMAPS = {("severity_to_priority", 1): [
    {"source_value": "5", "target_value": "P1", "provenance": "human"},
    {"source_value": "1", "target_value": "P4", "provenance": "human"},
]}

COLUMNS = ["finding_id", "priority", "inspection_method"]


def _normalized(findings):
    return {"header": {"inspection_name": "X"}, "findings": findings}


def test_oov_value_becomes_exception_never_a_guess():
    normalized = _normalized([
        {"id": "1", "severity": "5"},
        {"id": "2", "severity": "3"},  # 3 is NOT in the value map
    ])
    rows, exceptions = apply_records(DOC, normalized, {}, VMAPS, COLUMNS)
    assert len(rows) == 1 and rows[0]["finding_id"] == "1"
    assert len(exceptions) == 1
    exc = exceptions[0]
    assert exc["kind"] == "oov_value"
    assert exc["record_ref"] == "2"
    assert "'3'" in exc["detail"]["reason"]
    assert exc["detail"]["suggestion"]  # a resolution hint is mandatory (FR-012)
    # the failing record must not appear in output in any form
    assert all(r["finding_id"] != "2" for r in rows)


def test_parse_error_record_is_exception_document_still_converts():
    normalized = _normalized([
        {"id": "1", "severity": "5"},
        {"id": "2", "severity": "9 GARBLED", "parse_error": "severity '9 GARBLED' outside vocabulary"},
        {"id": "3", "severity": "1"},
    ])
    rows, exceptions = apply_records(DOC, normalized, {}, VMAPS, COLUMNS)
    assert [r["finding_id"] for r in rows] == ["1", "3"]  # document converts
    assert len(exceptions) == 1
    assert exceptions[0]["kind"] == "record_parse"
    assert exceptions[0]["record_ref"] == "2"


def test_clean_run_emits_exceptions_report(tmp_path):
    from rmu.render.exceptions import write_exceptions_report

    path = write_exceptions_report(tmp_path, [])  # zero exceptions
    assert path.exists()
    text = path.read_text()
    assert text.startswith("document,record_ref,kind,field,value,reason,suggestion")
    assert len(text.strip().splitlines()) == 1  # header only, but the report EXISTS
