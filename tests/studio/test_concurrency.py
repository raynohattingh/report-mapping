"""FR-005: cross-surface draft conflicts block the save — never silent.

The CLI/editor writes draft files directly, so locks are unenforceable;
optimistic concurrency on content hash detects any other writer. On conflict
the analyst explicitly chooses reload-latest or overwrite-with-mine;
overwrite applies the edit to the BASE the analyst saw (clobbering the other
writer), never merging into the changed file underneath.
"""

from __future__ import annotations

import hashlib

import pytest

from rmu.studio.concurrency import DraftConflict, DraftLease


@pytest.fixture
def draft(tmp_path):
    path = tmp_path / "session_1.transform.yaml"
    path.write_text("routes:\n  a: original\n", encoding="utf-8")
    return path


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_load_returns_text_and_content_hash(draft):
    lease = DraftLease()
    text, base_hash = lease.load(draft)
    assert text == "routes:\n  a: original\n"
    assert base_hash == _sha(text)


def test_clean_save_applies_edit(draft):
    lease = DraftLease()
    _, base_hash = lease.load(draft)
    new = lease.apply_edit(draft, base_hash, lambda t: t.replace("original", "edited"))
    assert new == "routes:\n  a: edited\n"
    assert draft.read_text(encoding="utf-8") == new


def test_conflicting_save_blocked_with_diff_and_file_untouched(draft):
    lease = DraftLease()
    _, base_hash = lease.load(draft)
    draft.write_text("routes:\n  a: changed-by-cli\n", encoding="utf-8")  # other writer

    with pytest.raises(DraftConflict) as exc:
        lease.apply_edit(draft, base_hash, lambda t: t.replace("original", "mine"))
    conflict = exc.value
    assert conflict.base_known
    assert "-  a: original" in conflict.diff
    assert "+  a: changed-by-cli" in conflict.diff
    # the blocked save changed nothing on disk
    assert draft.read_text(encoding="utf-8") == "routes:\n  a: changed-by-cli\n"


def test_overwrite_applies_edit_to_base_never_merging(draft):
    lease = DraftLease()
    _, base_hash = lease.load(draft)
    draft.write_text("routes:\n  a: changed-by-cli\n  b: added-by-cli\n",
                     encoding="utf-8")

    new = lease.apply_edit(draft, base_hash,
                           lambda t: t.replace("original", "mine"), overwrite=True)
    # my edit on MY base — the other writer's changes are clobbered, not merged
    assert new == "routes:\n  a: mine\n"
    assert "added-by-cli" not in draft.read_text(encoding="utf-8")


def test_overwrite_without_known_base_still_blocks(draft):
    fresh = DraftLease()  # e.g. server restarted: base content unknown
    stale_hash = _sha("routes:\n  a: original\n")
    draft.write_text("routes:\n  a: changed-by-cli\n", encoding="utf-8")

    with pytest.raises(DraftConflict) as exc:
        fresh.apply_edit(draft, stale_hash, lambda t: t, overwrite=True)
    assert not exc.value.base_known
    assert exc.value.diff is None
