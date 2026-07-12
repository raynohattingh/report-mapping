"""T012 (SC-003, FR-008): the strict proposal gate drops malformed and
unresolvable model output and counts drops by reason; valid proposals pass."""

import json

from rmu.ai.validation import gate_proposals

SOURCE_INVENTORY = {
    "header": {"inspection_name": "Line 7", "report_date": "2020-01-01"},
    "finding": {"id": "1", "severity": "3", "issues": ["Corrosion"], "comments": "x"},
}
TARGET_FIELDS = {"finding_id", "priority", "source_severity", "defect_code", "comments"}
OBSERVED = {"finding.severity": {"1", "3", "5", "?"}, "finding.issues": {"Corrosion"}}


def _gate(items):
    return gate_proposals(
        json.dumps(items),
        source_inventory=SOURCE_INVENTORY,
        target_fields=TARGET_FIELDS,
        observed_values=OBSERVED,
    )


def test_valid_proposal_passes_untouched():
    props, dropped = _gate([
        {"target_field": "finding_id", "from_path": "finding.id",
         "rationale": "annotation id is the natural key"},
    ])
    assert len(props) == 1
    assert props[0].target_field == "finding_id"
    assert props[0].tier == "T2"
    assert sum(dropped.values()) == 0


def test_schema_invalid_item_dropped():
    # missing rationale => schema failure
    props, dropped = _gate([
        {"target_field": "finding_id", "from_path": "finding.id"},
    ])
    assert props == []
    assert dropped["schema"] == 1


def test_unknown_target_field_dropped():
    props, dropped = _gate([
        {"target_field": "nonexistent_field", "from_path": "finding.id",
         "rationale": "n/a"},
    ])
    assert props == []
    assert dropped["unknown_field"] == 1


def test_unknown_from_path_dropped():
    props, dropped = _gate([
        {"target_field": "comments", "from_path": "finding.ghost",
         "rationale": "n/a"},
    ])
    assert props == []
    assert dropped["unknown_field"] == 1


def test_unobserved_value_entry_filtered_and_counted():
    props, dropped = _gate([
        {"target_field": "priority", "from_path": "finding.severity",
         "rationale": "severity to priority",
         "value_map_name": "severity_to_priority",
         "suggested_entries": [
             {"source_value": "3", "target_value": "P3"},   # observed -> kept
             {"source_value": "9", "target_value": "P9"},   # unobserved -> dropped
         ]},
    ])
    assert len(props) == 1
    kept = props[0].suggested_entries
    assert [e["source_value"] for e in kept] == ["3"]
    assert kept[0]["provenance"] == "ai-accepted"
    assert dropped["unknown_value"] == 1


def test_garbage_json_drops_all():
    props, dropped = gate_proposals(
        "this is not json",
        source_inventory=SOURCE_INVENTORY,
        target_fields=TARGET_FIELDS,
        observed_values=OBSERVED,
    )
    assert props == []
    assert sum(dropped.values()) >= 1


def test_mixed_batch_counts_each_reason():
    props, dropped = _gate([
        {"target_field": "finding_id", "from_path": "finding.id", "rationale": "natural key"},
        {"target_field": "finding_id", "from_path": "finding.id"},              # schema
        {"target_field": "ghost", "from_path": "finding.id", "rationale": "nope"},  # unknown_field
    ])
    assert len(props) == 1
    assert dropped["schema"] == 1
    assert dropped["unknown_field"] == 1
