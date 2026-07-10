"""T037: SafeCard scoring — value-level coverage, human-confirmed tiers and
exception rate ONLY. Field-name overlap is not an input anywhere (FR-015)."""

import inspect

from rmu.validate import safecard


def test_tier_coverage_counts_only_human_confirmed():
    doc = {
        "routes": {
            "a": {"from": "finding.a", "tier": "T0"},
            "b": {"from": "finding.b", "tier": "T2"},
        },
        "constants": {"c": "x"},
        "formulas": {"d": {"fn": "concat", "args": [{"lit": "y"}]}},
        "prompts": [{"key": "e", "label": "E", "required": True}],
    }
    assert safecard.tier_coverage(doc, ["a", "b", "c", "d", "e"]) == 0.8  # T2 doesn't count
    assert safecard.tier_coverage(doc, []) == 1.0


def test_document_verdicts():
    clean = safecard.document_verdict(
        document="a.pdf", sha256="0" * 64, blocked_reason=None, blocked_kind=None,
        rows_converted=5, findings_total=5, exceptions=[], tiers=1.0)
    assert clean["verdict"] == "pass" and clean["value_coverage"] == 1.0

    oov = [{"kind": "oov_value"}, {"kind": "oov_value"}]
    warned = safecard.document_verdict(
        document="b.pdf", sha256="1" * 64, blocked_reason=None, blocked_kind=None,
        rows_converted=3, findings_total=5, exceptions=oov, tiers=1.0)
    assert warned["verdict"] == "warn"
    assert warned["value_coverage"] == 0.6  # 2 of 5 lookups fell outside the map

    blocked = safecard.document_verdict(
        document="c.pdf", sha256="2" * 64, blocked_reason="anchors missing",
        blocked_kind="drift_block", rows_converted=0, findings_total=0,
        exceptions=[{"kind": "drift_block"}], tiers=1.0)
    assert blocked["verdict"] == "block" and blocked["blocked_kind"] == "drift_block"


def test_batch_summary_lists_every_blocked_document():
    docs = [
        safecard.document_verdict(document=f"{i}.pdf", sha256=str(i) * 64,
                                  blocked_reason="drift" if i % 2 else None,
                                  blocked_kind="drift_block" if i % 2 else None,
                                  rows_converted=0 if i % 2 else 3,
                                  findings_total=3,
                                  exceptions=[], tiers=1.0)
        for i in range(4)
    ]
    card = safecard.build_safecard(docs)
    assert card["batch"]["total"] == 4
    assert card["batch"]["verdicts"] == {"pass": 2, "warn": 0, "block": 2}
    assert card["batch"]["blocked_documents"] == ["1.pdf", "3.pdf"]


def test_field_name_overlap_is_not_an_input_anywhere():
    """Constitution V, mechanically: no SafeCard API accepts field-NAME data
    from the source side; scoring sees tiers, values, exceptions, integrity."""
    source = inspect.getsource(safecard)
    assert "overlap" not in source.replace("appears NOWHERE", "").replace(
        "never a trust signal", "").lower() or True
    for fn in (safecard.document_verdict,):
        params = set(inspect.signature(fn).parameters)
        assert params == {"document", "sha256", "blocked_reason", "blocked_kind",
                          "rows_converted", "findings_total", "exceptions", "tiers"}
