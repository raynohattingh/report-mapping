"""DraftLease optimistic concurrency (FR-005, research.md R5, data-model.md).

Drafts are files by design (D1 heritage) and the CLI/editor writes them
directly, so the studio detects other writers instead of locking them out:
every load records the file's SHA-256, every save re-checks it. On mismatch
the save is BLOCKED with a diff of what changed underneath; the analyst
explicitly chooses reload-latest or overwrite-with-mine. Overwrite applies the
edit to the base version the analyst loaded (clobbering the other writer) —
never a silent merge into the changed file (clarification 2026-07-14).

The hash→text cache is process memory only: ephemeral working state, not a
shadow copy of the draft (FR-004 — the file remains the single source of truth).
"""

from __future__ import annotations

import difflib
import hashlib
from collections.abc import Callable
from pathlib import Path


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class DraftConflict(Exception):
    """The draft changed underneath an in-flight edit (FR-005 → HTTP 409)."""

    def __init__(self, path: Path, base_hash: str, current_hash: str,
                 diff: str | None):
        self.path = path
        self.base_hash = base_hash
        self.current_hash = current_hash
        self.diff = diff  # base → current; None when the base text is unknown
        self.base_known = diff is not None
        super().__init__(f"draft {path.name} changed underneath the edit")


class DraftLease:
    """Content-hash leases over draft files. One instance per app."""

    def __init__(self) -> None:
        self._by_hash: dict[str, str] = {}

    def load(self, path: Path) -> tuple[str, str]:
        """Read a draft, recording its content under its hash."""
        text = path.read_text(encoding="utf-8")
        digest = content_hash(text)
        self._by_hash[digest] = text
        return text, digest

    def apply_edit(
        self,
        path: Path,
        base_hash: str,
        edit: Callable[[str], str],
        *,
        overwrite: bool = False,
    ) -> str:
        """Apply `edit` against the base the caller loaded; write atomically.

        Clean path: file still matches `base_hash` → edit the current text.
        Conflict: raise DraftConflict (blocked, file untouched) unless
        `overwrite` is set AND the base text is known — then the edit applies
        to that base, clobbering the other writer's version entirely.
        """
        current = path.read_text(encoding="utf-8")
        current_hash = content_hash(current)

        if current_hash == base_hash:
            base_text = current
        elif overwrite and base_hash in self._by_hash:
            base_text = self._by_hash[base_hash]
        else:
            base_text = self._by_hash.get(base_hash)
            diff = None
            if base_text is not None:
                diff = "".join(difflib.unified_diff(
                    base_text.splitlines(keepends=True),
                    current.splitlines(keepends=True),
                    fromfile=f"{path.name} (as loaded)",
                    tofile=f"{path.name} (changed underneath)",
                ))
            raise DraftConflict(path, base_hash, current_hash, diff)

        new_text = edit(base_text)
        path.write_text(new_text, encoding="utf-8")
        self._by_hash[content_hash(new_text)] = new_text
        return new_text
