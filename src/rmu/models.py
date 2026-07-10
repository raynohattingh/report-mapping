"""SQLAlchemy models per specs/001-report-mapping-v1/data-model.md.

★ tables (SourceProfile, TargetTemplate, Transform, ValueMap, ApplyRun) are
versioned, append-only, effective-dated (Constitution III, design §8).
Enforcement lives in rmu.db; the sets below declare which classes it guards.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSON, list: JSON}


class SourceProfile(Base):
    __tablename__ = "source_profiles"
    __table_args__ = (UniqueConstraint("key", "structural_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(120))
    structural_version: Mapped[str] = mapped_column(String(40))
    platform: Mapped[str] = mapped_column(String(40))
    export_kind: Mapped[str] = mapped_column(String(40))
    job_type: Mapped[str] = mapped_column(String(40))
    fingerprint: Mapped[dict] = mapped_column(JSON)
    extractor_ref: Mapped[str] = mapped_column(String(200))
    declared_totals_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|superseded
    effective_from: Mapped[datetime.date] = mapped_column(Date)


class TargetTemplate(Base):
    __tablename__ = "target_templates"
    __table_args__ = (UniqueConstraint("name", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    institution: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer)
    effective_from: Mapped[datetime.date] = mapped_column(Date)
    template_files: Mapped[dict] = mapped_column(JSON, default=dict)
    required_schema: Mapped[dict] = mapped_column(JSON)
    validation_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    # Constitution I: both shipped templates are INTERIM stand-ins (A2, SC-008).
    interim: Mapped[bool] = mapped_column(Boolean, default=True)


class Transform(Base):
    __tablename__ = "transforms"
    __table_args__ = (UniqueConstraint("source_profile_id", "target_template_id", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_profile_id: Mapped[int] = mapped_column(ForeignKey("source_profiles.id"))
    target_template_id: Mapped[int] = mapped_column(ForeignKey("target_templates.id"))
    version: Mapped[int] = mapped_column(Integer)
    effective_from: Mapped[datetime.date] = mapped_column(Date)
    yaml_body: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[str] = mapped_column(String(80))
    approved_at: Mapped[datetime.datetime] = mapped_column(DateTime)
    parent_version: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ValueMap(Base):
    __tablename__ = "value_maps"
    __table_args__ = (UniqueConstraint("name", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer)
    # entries: [{source_value, target_value, provenance: human|ai-accepted, note?}]
    entries: Mapped[list] = mapped_column(JSON)
    effective_from: Mapped[datetime.date] = mapped_column(Date)


class MappingSession(Base):
    __tablename__ = "mapping_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_profile_id: Mapped[int] = mapped_column(ForeignKey("source_profiles.id"))
    target_template_id: Mapped[int] = mapped_column(ForeignKey("target_templates.id"))
    exemplar_document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id"))
    mode: Mapped[str] = mapped_column(String(10))  # ai|manual (FR-010)
    # proposals: [{target_field, from, value_map?, tier, rationale, at}] (FR-005, FR-021)
    proposals: Mapped[list] = mapped_column(JSON, default=list)
    # decisions: [{target_field, action, detail, at}] (FR-021)
    decisions: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(12), default="draft")  # draft|approved|abandoned
    resulting_transform_id: Mapped[int | None] = mapped_column(
        ForeignKey("transforms.id"), nullable=True
    )


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_profiles.id"), nullable=True
    )  # null = unrecognized -> quarantine (FR-002)
    received_at: Mapped[datetime.datetime] = mapped_column(DateTime)  # audit only, never output
    extraction_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ApplyRun(Base):
    __tablename__ = "apply_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_label: Mapped[str] = mapped_column(String(120))
    document_shas: Mapped[list] = mapped_column(JSON)
    prompt_answers: Mapped[dict] = mapped_column(JSON, default=dict)  # replayed on regen (FR-017)
    transform_id: Mapped[int] = mapped_column(ForeignKey("transforms.id"))
    target_template_id: Mapped[int] = mapped_column(ForeignKey("target_templates.id"))
    safecard: Mapped[dict] = mapped_column(JSON)
    outputs_manifest: Mapped[list] = mapped_column(JSON)  # [{document_sha, output_kind, store_hash}]
    exceptions_report_ref: Mapped[str] = mapped_column(String(64))  # ALWAYS present (FR-013)
    # Written only on successful completion (interrupted-run edge case, analysis C4).
    completed_at: Mapped[datetime.datetime] = mapped_column(DateTime)


class ConversionException(Base):
    __tablename__ = "exceptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    apply_run_id: Mapped[int] = mapped_column(ForeignKey("apply_runs.id"))
    document_sha: Mapped[str] = mapped_column(String(64))
    record_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)  # null = doc-level
    # oov_value | record_parse | drift_block | unknown_profile | duplicate
    kind: Mapped[str] = mapped_column(String(20))
    detail: Mapped[dict] = mapped_column(JSON)  # failing value, reason, suggestion (FR-012)
    status: Mapped[str] = mapped_column(String(10), default="open")  # open|resolved
    resolution: Mapped[dict | None] = mapped_column(JSON, nullable=True)


#: Classes guarded by the append-only listener in rmu.db (Constitution III).
APPEND_ONLY_MODELS = (SourceProfile, TargetTemplate, Transform, ValueMap, ApplyRun)
