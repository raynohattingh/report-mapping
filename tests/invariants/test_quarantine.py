"""T034 — the SC-001 held-out fixture is QUARANTINED: no source or test code
may reference the holdout directory or the Zeitview fixture. The only
legitimate consumer is the human-run acceptance protocol
(scripts/acceptance_003.md). This test is the enforcement."""

from __future__ import annotations

from pathlib import Path

FORBIDDEN = ("seed/holdout", "zeitview")
ALLOWED = {Path(__file__).resolve()}  # only this enforcement file may say the words


def _code_files() -> list[Path]:
    files: list[Path] = []
    for root in (Path("src"), Path("tests")):
        files += [p for p in root.rglob("*.py") if p.resolve() not in ALLOWED]
    return files


def test_no_code_references_the_quarantined_fixture():
    offenders = []
    for path in _code_files():
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for needle in FORBIDDEN:
            if needle in text:
                offenders.append(f"{path}: contains {needle!r}")
    assert not offenders, (
        "SC-001 quarantine violated - dev code must never touch the held-out "
        "fixture:\n" + "\n".join(offenders)
    )
