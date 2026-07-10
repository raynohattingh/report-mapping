"""Idempotent seed loading: profiles, interim templates, defect-code vocabulary.

Everything here is loaded AS DATA (Constitution IV): profiles/*.yaml,
templates/*/, seed/defect_codes_v1.csv. Re-running never duplicates rows —
registries are append-only, so presence is checked by natural key.
"""

from __future__ import annotations

import csv
import datetime
import json
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from rmu import store
from rmu.config import REPO_ROOT
from rmu.models import SourceProfile, TargetTemplate

SEED_EFFECTIVE = datetime.date(2026, 7, 11)
DEFECT_CODES_CSV = REPO_ROOT / "seed" / "defect_codes_v1.csv"


def load_defect_codes(csv_path: Path | None = None) -> list[dict]:
    """Interim target defect vocabulary (A2) — data, never hardcoded."""
    path = csv_path or DEFECT_CODES_CSV
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def profile_config(key_at_version: str) -> dict:
    """Load the profile YAML for e.g. 'scopito.pdf.powerline@v2020'."""
    key, _, sv = key_at_version.partition("@")
    path = REPO_ROOT / "profiles" / f"{key}.{sv}.yaml"
    return yaml.safe_load(path.read_text())


def seed_profiles(session: Session) -> list[str]:
    added = []
    for path in sorted((REPO_ROOT / "profiles").glob("*.yaml")):
        cfg = yaml.safe_load(path.read_text())
        exists = session.scalar(
            select(SourceProfile).where(
                SourceProfile.key == cfg["key"],
                SourceProfile.structural_version == cfg["structural_version"],
            )
        )
        if exists:
            continue
        session.add(
            SourceProfile(
                key=cfg["key"],
                structural_version=cfg["structural_version"],
                platform=cfg["platform"],
                export_kind=cfg["export_kind"],
                job_type=cfg["job_type"],
                fingerprint=cfg["fingerprint"],
                extractor_ref=cfg["extractor_ref"],
                declared_totals_fields=cfg.get("header", {}),
                effective_from=cfg["effective_from"],
            )
        )
        added.append(f"{cfg['key']}@{cfg['structural_version']}")
    return added


def seed_templates(session: Session) -> list[str]:
    added = []
    for tdir in sorted((REPO_ROOT / "templates").iterdir()):
        if not tdir.is_dir():
            continue
        meta = json.loads((tdir / "template.json").read_text())
        name = tdir.name
        exists = session.scalar(
            select(TargetTemplate).where(
                TargetTemplate.name == name, TargetTemplate.version == 1
            )
        )
        if exists:
            continue
        files = {
            p.name: store.put_file(p)
            for p in sorted(tdir.iterdir())
            if p.is_file() and p.suffix != ".py"
        }
        session.add(
            TargetTemplate(
                institution="INTERIM",  # Constitution I: no real institution content
                name=name,
                version=1,
                effective_from=SEED_EFFECTIVE,
                template_files=files,
                required_schema=json.loads((tdir / "schema.json").read_text()),
                validation_rules=json.loads((tdir / "rules.json").read_text()),
                interim=bool(meta.get("interim", True)),
            )
        )
        added.append(f"{name}@1")
    return added


def seed_all(session: Session) -> dict:
    profiles = seed_profiles(session)
    templates = seed_templates(session)
    codes = load_defect_codes()
    session.commit()
    return {"profiles": profiles, "templates": templates, "defect_codes": len(codes)}
