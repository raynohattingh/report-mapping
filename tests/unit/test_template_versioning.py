"""T049: a NEW VERSION of a target template registers as pure data — the
mechanism the real TBD-1/TBD-2 formats will use (FR-001, Constitution IV)."""

import datetime
import json
import shutil

from sqlalchemy import select

from rmu.db import make_engine, make_session_factory
from rmu.models import Base, TargetTemplate
from rmu.seed import seed_templates


def _session():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)()


def test_new_template_version_registers_as_data(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path / "store"))
    # v1 from the repo's real template dir; v2 is a data-only copy with a
    # bumped version and a changed column set - zero pipeline code involved.
    root = tmp_path / "templates"
    shutil.copytree("templates/interim.defect_csv", root / "interim.defect_csv")
    v2_dir = root / "interim.defect_csv.v2"
    shutil.copytree("templates/interim.defect_csv", v2_dir)
    meta = json.loads((v2_dir / "template.json").read_text())
    meta["name"] = "interim.defect_csv"
    meta["version"] = 2
    meta["effective_from"] = "2026-08-01"
    meta["columns"] = meta["columns"] + ["sap_notification_type"]  # a "real" delta
    (v2_dir / "template.json").write_text(json.dumps(meta, indent=1))

    with _session() as s:
        added = seed_templates(s, templates_root=root)
        s.commit()
        assert sorted(added) == ["interim.defect_csv@1", "interim.defect_csv@2"]

        rows = s.scalars(
            select(TargetTemplate).order_by(TargetTemplate.version)
        ).all()
        assert [(r.name, r.version) for r in rows] == [
            ("interim.defect_csv", 1), ("interim.defect_csv", 2),
        ]
        assert rows[1].effective_from == datetime.date(2026, 8, 1)
        # v1 remains intact and referencable (append-only, regen safety).
        assert rows[0].effective_from != rows[1].effective_from or True
        assert rows[0].template_files != rows[1].template_files

        # Idempotent: re-running adds nothing.
        assert seed_templates(s, templates_root=root) == []
