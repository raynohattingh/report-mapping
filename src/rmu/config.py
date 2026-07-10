"""Runtime configuration.

SQLite by default; Postgres is a config change (D4, A5). The store directory
holds content-addressed blobs and run outputs (research R3/R9).
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def db_url() -> str:
    return os.environ.get("RMU_DB_URL", f"sqlite:///{store_root() / 'rmu.db'}")


def store_root() -> Path:
    root = Path(os.environ.get("RMU_STORE", REPO_ROOT / "store"))
    root.mkdir(parents=True, exist_ok=True)
    return root
