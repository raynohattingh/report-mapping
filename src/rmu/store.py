"""Content-addressed blob store (research R3).

`store/objects/<sha256[:2]>/<sha256>` — write-once; an existing hash
short-circuits. Regeneration (FR-017/18) retrieves inputs by fingerprint.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from rmu.config import store_root


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _object_path(sha: str) -> Path:
    return store_root() / "objects" / sha[:2] / sha


def put_bytes(data: bytes) -> str:
    sha = sha256_bytes(data)
    path = _object_path(sha)
    if not path.exists():  # write-once
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.rename(path)
    return sha


def put_file(source: Path) -> str:
    return put_bytes(Path(source).read_bytes())


def get_bytes(sha: str) -> bytes:
    return _object_path(sha).read_bytes()


def get_path(sha: str) -> Path:
    path = _object_path(sha)
    if not path.exists():
        raise FileNotFoundError(f"no object {sha} in store")
    return path


def runs_dir(run_label: str) -> Path:
    d = store_root() / "runs" / run_label
    d.mkdir(parents=True, exist_ok=True)
    return d


def drafts_dir() -> Path:
    d = store_root() / "drafts"
    d.mkdir(parents=True, exist_ok=True)
    return d
