import datetime

import pytest

from rmu.db import make_engine, make_session_factory
from rmu.mapping import loader
from rmu.models import Base, ValueMap

VALID = """
meta:
  source_profile: scopito.pdf.powerline@v2020
  target_template: interim.defect_csv@1
  version: 1
routes:
  priority:
    from: finding.severity
    tier: T1
    value_map: {name: severity_to_priority, version: 1}
constants:
  inspection_method: "UAV visual"
formulas:
  report_ref:
    fn: concat
    args: [{field: header.company}, {lit: "-"}, {field: header.report_date}]
prompts:
  - {key: contract_number, label: "Client contract number", required: true}
"""


def test_valid_transform_parses():
    doc = loader.parse_transform(VALID)
    assert doc["meta"]["version"] == 1
    assert loader.routed_fields(doc) == {
        "priority",
        "inspection_method",
        "report_ref",
        "contract_number",
    }


def test_value_map_version_is_required():
    bad = VALID.replace("value_map: {name: severity_to_priority, version: 1}",
                        "value_map: {name: severity_to_priority}")
    with pytest.raises(loader.TransformValidationError, match="version"):
        loader.parse_transform(bad)


def test_unknown_formula_fn_rejected():
    bad = VALID.replace("fn: concat", "fn: eval")
    with pytest.raises(loader.TransformValidationError):
        loader.parse_transform(bad)


def test_arg_outside_grammar_rejected():
    bad = VALID.replace("{field: header.company}", "{shell: 'date'}")
    with pytest.raises(loader.TransformValidationError):
        loader.parse_transform(bad)


def test_missing_required_and_unreviewed():
    doc = loader.parse_transform(VALID)
    assert loader.missing_required(doc, ["priority", "defect_code"]) == ["defect_code"]
    doc2 = loader.parse_transform(VALID.replace("tier: T1", "tier: T2"))
    assert loader.unreviewed_fields(doc2) == ["priority"]


def test_unresolved_value_map_pins():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as s:
        doc = loader.parse_transform(VALID)
        assert loader.unresolved_value_maps(doc, s) != []
        s.add(ValueMap(name="severity_to_priority", version=1, entries=[],
                       effective_from=datetime.date(2026, 7, 11)))
        s.commit()
        assert loader.unresolved_value_maps(doc, s) == []
