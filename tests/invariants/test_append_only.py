"""Constitution III invariant: versioned registries are append-only (never cut, D3).

UPDATE or DELETE on SourceProfile / TargetTemplate / Transform / ValueMap / ApplyRun
(design §8 ★ tables; analysis C2 added ApplyRun) must raise AppendOnlyViolation.
Alembic migrations must stay additive on those tables (research R2).
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

import pytest

from rmu.db import AppendOnlyViolation, make_engine, make_session_factory
from rmu.models import (
    ApplyRun,
    Base,
    SourceProfile,
    TargetTemplate,
    Transform,
    ValueMap,
)

STAR_TABLES = ("source_profiles", "target_templates", "transforms", "value_maps", "apply_runs")


@pytest.fixture()
def session():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with factory() as s:
        yield s


def _seed_one_of_each(s):
    profile = SourceProfile(
        key="scopito.pdf.powerline",
        structural_version="v2020",
        platform="scopito",
        export_kind="pdf",
        job_type="powerline",
        fingerprint={"required_text": ["Severity overview"]},
        extractor_ref="rmu.extract.scopito_pdf_powerline",
        declared_totals_fields={"annotations": "annotations"},
        effective_from=datetime.date(2026, 7, 11),
    )
    template = TargetTemplate(
        institution="INTERIM",
        name="interim.defect_csv",
        version=1,
        effective_from=datetime.date(2026, 7, 11),
        template_files={},
        required_schema={"required": ["finding_id"]},
        validation_rules={},
        interim=True,
    )
    vmap = ValueMap(
        name="severity_to_priority",
        version=1,
        entries=[{"source_value": "5", "target_value": "P1", "provenance": "human"}],
        effective_from=datetime.date(2026, 7, 11),
    )
    s.add_all([profile, template, vmap])
    s.flush()
    transform = Transform(
        source_profile_id=profile.id,
        target_template_id=template.id,
        version=1,
        effective_from=datetime.date(2026, 7, 11),
        yaml_body="meta: {}",
        approved_by="rayno",
        approved_at=datetime.datetime(2026, 7, 11, 12, 0, 0),
    )
    s.add(transform)
    s.flush()
    run = ApplyRun(
        batch_label="b1",
        document_shas=["ab" * 32],
        prompt_answers={},
        transform_id=transform.id,
        target_template_id=template.id,
        safecard={"batch": "pass"},
        outputs_manifest=[],
        exceptions_report_ref="cd" * 32,
        completed_at=datetime.datetime(2026, 7, 11, 12, 0, 0),
    )
    s.add(run)
    s.commit()
    return profile, template, transform, vmap, run


def test_update_on_star_tables_raises(session):
    profile, template, transform, vmap, run = _seed_one_of_each(session)
    for obj, attr, newval in [
        (profile, "extractor_ref", "elsewhere"),
        (template, "institution", "ESKOM"),
        (transform, "yaml_body", "meta: {tampered: true}"),
        (vmap, "entries", []),
        (run, "outputs_manifest", [{"tampered": True}]),
    ]:
        setattr(obj, attr, newval)
        with pytest.raises(AppendOnlyViolation):
            session.flush()
        session.rollback()


def test_delete_on_star_tables_raises(session):
    objs = _seed_one_of_each(session)
    for obj in objs:
        session.delete(obj)
        with pytest.raises(AppendOnlyViolation):
            session.flush()
        session.rollback()


def test_new_versions_are_allowed(session):
    """Append-only means new versions insert freely (Constitution III)."""
    _, template, _, vmap, _ = _seed_one_of_each(session)
    session.add(
        ValueMap(
            name=vmap.name,
            version=2,
            entries=[{"source_value": "?", "target_value": "POI", "provenance": "human"}],
            effective_from=datetime.date(2026, 7, 12),
        )
    )
    session.commit()  # must not raise


def test_migrations_are_additive_on_star_tables():
    versions = sorted(Path("alembic/versions").glob("*.py"))
    assert versions, "expected at least the baseline migration"
    forbidden = re.compile(
        r"op\.(drop_table|drop_column|alter_column|rename_table)\(\s*['\"]("
        + "|".join(STAR_TABLES)
        + r")['\"]"
    )
    for vf in versions:
        hits = forbidden.findall(vf.read_text())
        assert not hits, f"destructive migration op on append-only table in {vf.name}: {hits}"
