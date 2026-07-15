"""Parity harness (FR-001/FR-002/FR-003, SC-002/SC-005/SC-006 foundation).

Compares a studio action against the equivalent CLI/library action performed
on a copy of the same draft, asserting BYTE equality of the resulting files.
Both surfaces edit drafts through split_draft/render_draft (banner preserved,
canonical yaml), so identical decisions must yield identical bytes — any
divergence is a studio-grew-business-logic defect.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from rmu.mapping.session import render_draft, split_draft


def library_edit(draft_path: Path, mutate: Callable[[dict], None]) -> bytes:
    """The reference result: apply `mutate` to a COPY the way any script or
    analyst tooling would (split → edit doc → canonical render)."""
    copy = draft_path.with_suffix(".parity-copy.yaml")
    shutil.copyfile(draft_path, copy)
    banner, doc = split_draft(copy.read_text(encoding="utf-8"))
    mutate(doc)
    expected = render_draft(banner, doc)
    copy.unlink()
    return expected.encode("utf-8")


def assert_studio_matches_library(
    draft_path: Path,
    mutate: Callable[[dict], None],
    studio_action: Callable[[], object],
):
    """Run `studio_action` (an HTTP call or the function a route delegates to)
    and assert the draft now equals the library-path result byte-for-byte."""
    expected = library_edit(draft_path, mutate)
    response = studio_action()
    actual = draft_path.read_bytes()
    assert actual == expected, (
        "studio edit diverged from the library-path edit for the same decision"
    )
    return response
