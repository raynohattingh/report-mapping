import copy
from pathlib import Path

from rmu.onboard.analyze_target import analyze
from rmu.onboard.interpret_matrix import apply_interpretation

FIXTURE = Path("tests/fixtures/onboarding/matrix_target.pdf")


def test_noai_reconstruction_is_deterministic_and_unassisted():
    """Verify analyze() is pure, repeatable, and contains no ai_assist evidence."""
    a = analyze(FIXTURE, kind="fixed_layout")
    b = analyze(FIXTURE, kind="fixed_layout")
    assert a == b  # pure, repeatable
    for e in a["elements"]:
        assert "ai_assist" not in e.get("evidence", {})


def test_interpret_noop_without_interpreter_leaves_axes_untouched():
    """Verify apply_interpretation with interpreter=None is a strict no-op.

    apply_interpretation mutates in place and returns the same object.
    We use deepcopy to capture state BEFORE the call to ensure the assertion
    is real, not just an identity check.
    """
    doc = analyze(FIXTURE, kind="fixed_layout")
    doc_before = copy.deepcopy(doc)
    grids = {1: [["No", "Criterion", "T1", "T2", "T3"]]}
    same, dropped = apply_interpretation(doc, grids, None)

    # Verify no-op: doc should be unchanged
    assert same is doc
    assert doc == doc_before
    assert dropped == {"unknown_index": 0, "unmatched_axis_entry": 0}
