"""Dashboard read model (US6, FR-038/FR-039) — read-only queries only.

Everything here is derived from the same rows/blobs the CLI listings read;
the studio adds no state. Approved/registered artifacts are surfaced without
any mutating affordance (FR-006).
"""

from __future__ import annotations

import csv
import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from rmu import store as blobstore
from rmu.models import (
    ApplyRun,
    MappingSession,
    OnboardingProposal,
    SourceProfile,
    TargetTemplate,
    Transform,
    ValueMap,
)


def overview(s: Session) -> dict:
    profiles = [
        {"ref": f"{p.key}@{p.structural_version}", "status": p.status,
         "effective": str(p.effective_from)}
        for p in s.scalars(select(SourceProfile).order_by(SourceProfile.key))
    ]
    templates = [
        {"ref": f"{t.name}@{t.version}", "interim": t.interim,
         "effective": str(t.effective_from)}
        for t in s.scalars(select(TargetTemplate).order_by(
            TargetTemplate.name, TargetTemplate.version))
    ]
    transforms = [
        {"id": t.id, "version": t.version, "approved_by": t.approved_by,
         "profile_id": t.source_profile_id, "template_id": t.target_template_id}
        for t in s.scalars(select(Transform).order_by(Transform.id))
    ]
    value_maps = [
        {"ref": f"{v.name}@{v.version}", "entries": len(v.entries)}
        for v in s.scalars(select(ValueMap).order_by(ValueMap.name, ValueMap.version))
    ]
    sessions = [
        {"id": ms.id, "mode": ms.mode, "status": ms.status}
        for ms in s.scalars(select(MappingSession).order_by(MappingSession.id))
    ]
    proposals = [
        {"id": p.id, "kind": p.kind, "status": p.status}
        for p in s.scalars(select(OnboardingProposal).order_by(OnboardingProposal.id))
    ]
    runs = [
        {"id": r.id, "label": r.batch_label,
         "batch": r.safecard["batch"], "transform_id": r.transform_id}
        for r in s.scalars(select(ApplyRun).order_by(ApplyRun.id))
    ]
    return {
        "profiles": profiles, "templates": templates, "transforms": transforms,
        "value_maps": value_maps, "sessions": sessions, "proposals": proposals,
        "runs": runs,
    }


def run_detail(s: Session, run_id: int) -> dict | None:
    run = s.get(ApplyRun, run_id)
    if run is None:
        return None
    safecard = run.safecard
    exceptions: list[dict] = []
    if run.exceptions_report_ref:
        try:
            text = blobstore.get_bytes(run.exceptions_report_ref).decode("utf-8")
            exceptions = list(csv.DictReader(io.StringIO(text)))
        except FileNotFoundError:
            exceptions = []
    profile = s.get(SourceProfile, _run_profile_id(s, run))
    return {
        "id": run.id, "label": run.batch_label,
        "batch": safecard["batch"],
        "documents": safecard.get("documents", []),
        "blocked": safecard["batch"].get("blocked_documents", []),
        "exceptions": exceptions,
        "outputs_manifest": run.outputs_manifest,
        "seed_profile": (f"{profile.key}@{profile.structural_version}"
                         if profile else ""),
    }


def _run_profile_id(s: Session, run: ApplyRun) -> int | None:
    transform = s.get(Transform, run.transform_id)
    return transform.source_profile_id if transform else None
