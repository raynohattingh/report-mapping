"""FR-020 / Constitution II+VII, mechanically enforced (analysis C3).

Importing the deterministic pipeline stages must not pull in any AI or network
client module. Runs in a fresh subprocess so this test session's own imports
can't contaminate the check.
"""

import subprocess
import sys

BANNED = ["anthropic", "httpx", "requests", "rmu.mapping.providers", "rmu.ai", "fastembed"]

CHECK = f"""
import sys
import rmu.apply, rmu.detect, rmu.extract, rmu.validate, rmu.render
import rmu.apply.engine, rmu.extract.scopito_pdf_powerline, rmu.detect.fingerprint
loaded = [m for m in {BANNED!r} if m in sys.modules]
assert not loaded, f"AI/network modules reachable from deterministic stages: {{loaded}}"
print("clean")
"""


def test_apply_path_imports_no_ai_or_network():
    result = subprocess.run(
        [sys.executable, "-c", CHECK], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "clean" in result.stdout
