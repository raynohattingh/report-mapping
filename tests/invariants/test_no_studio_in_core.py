"""FR-042 / Constitution VI, mechanically enforced (feature 004, D6).

The studio is a surface, not a stage: no pipeline, mapping, onboarding, apply
or render module may import it. Two guards:

1. Import-time: loading every core package in a fresh subprocess must not pull
   `rmu.studio` (or the studio-only web deps) into sys.modules — the same
   pattern as test_no_ai_in_apply.py.
2. Static: no `import rmu.studio` / `from rmu.studio` statement anywhere under
   the core packages, so even a lazy (function-body) import is rejected. The
   single allowed reference is the lazy probe in rmu/cli.py (a surface).
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

CORE_PACKAGES = ["detect", "extract", "mapping", "apply", "validate", "render",
                 "onboard", "ai"]
BANNED = ["rmu.studio", "fastapi", "uvicorn", "starlette"]

CHECK = f"""
import sys
import rmu.detect, rmu.extract, rmu.mapping, rmu.apply, rmu.validate, rmu.render
import rmu.onboard, rmu.ai
import rmu.mapping.session, rmu.mapping.approve, rmu.mapping.loader
import rmu.apply.engine, rmu.apply.batch, rmu.onboard.proposal, rmu.onboard.approve
loaded = [m for m in {BANNED!r} if m in sys.modules]
assert not loaded, f"studio/web modules reachable from core stages: {{loaded}}"
print("clean")
"""


def test_core_imports_never_load_studio():
    result = subprocess.run(
        [sys.executable, "-c", CHECK], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "clean" in result.stdout


def test_no_static_studio_import_in_core_sources():
    src = Path(__file__).resolve().parents[2] / "src" / "rmu"
    offenders: list[str] = []
    for package in CORE_PACKAGES:
        for path in (src / package).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    if name == "rmu.studio" or name.startswith("rmu.studio."):
                        offenders.append(f"{path.relative_to(src)}:{node.lineno}")
    assert not offenders, f"core modules import rmu.studio: {offenders}"
