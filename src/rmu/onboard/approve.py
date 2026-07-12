"""Verify-on-approve gate + registration (FR-017/FR-022/FR-024, D5).

Approval is a machine-checked PROOF, not a signature: the corrected recipe is
re-run deterministically against every exemplar and must reproduce what the
analyst confirmed; the fingerprint must match the exemplars AND collide with
no active registered profile. Only then does a registry row appear. Failures
persist the verify report and leave the proposal in draft.
"""

from __future__ import annotations

import datetime

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from rmu import store
from rmu.config import profiles_root
from rmu.detect.fingerprint import matches_fingerprint
from rmu.extract.recipe_pdf import extract
from rmu.models import SourceProfile
from rmu.onboard.proposal import Proposal
from rmu.onboard.schemas import validate_recipe


class VerifyFailure(RuntimeError):
    """Verify-on-approve failed; proposal stays draft with the report persisted."""

    def __init__(self, report: dict):
        self.report = report
        failed = [c for c in report["checks"] if not c["ok"]]
        super().__init__(
            "verify-on-approve failed: "
            + "; ".join(f"{c['check']}: {c['detail']}" for c in failed)
        )


def _active_payload(element: dict) -> dict:
    return element.get("corrected_payload") or element["payload"]


def _elements(document: dict, kind: str) -> list[dict]:
    """Elements of one kind that survived review (confirmed or corrected)."""
    return [
        e
        for e in document["elements"]
        if e["element_kind"] == kind and e["review_state"] in ("confirmed", "corrected")
    ]


def recipe_from_elements(document: dict, key: str, version: str) -> dict:
    """Assemble the registered recipe from human-validated elements only.
    Removed elements vanish; corrected ones use the analyst's payload."""
    tables = _elements(document, "record_table")
    if not tables:
        raise VerifyFailure(
            {"ok": False, "checks": [{"check": "recipe_assembly", "ok": False,
             "detail": "no confirmed record_table element - nothing to extract"}]}
        )
    table = _active_payload(tables[0])
    fingerprint: dict = {
        "required_text": [
            _active_payload(e)["required_text"]
            for e in _elements(document, "fingerprint_anchor")
        ]
    }
    header_regex = table.get("detection", {}).get("table_header_regex")
    if header_regex:
        fingerprint["table_header_regex"] = header_regex
    if not fingerprint["required_text"] and not header_regex:
        raise VerifyFailure(
            {"ok": False, "checks": [{"check": "recipe_assembly", "ok": False,
             "detail": "no confirmed fingerprint elements (FR-024)"}]}
        )

    parts = key.split(".")
    recipe = {
        "key": key,
        "structural_version": version,
        "platform": parts[0],
        "export_kind": "pdf",
        "job_type": parts[-1],
        "extractor_ref": "rmu.extract.recipe_pdf",
        "effective_from": datetime.date.today().isoformat(),
        "fingerprint": fingerprint,
        "records": {
            "detection": table["detection"],
            "columns": [
                {"name": _active_payload(e)["name"]}
                for e in _elements(document, "record_column")
            ],
            **({"continuation": table["continuation"]} if table.get("continuation") else {}),
        },
    }
    images = [_active_payload(e) for e in _elements(document, "image_region")]
    if images:
        recipe["images"] = images
    furniture = [_active_payload(e)["text"] for e in _elements(document, "furniture_line")]
    if furniture:
        recipe["furniture"] = furniture
    header_fields = []
    for e in _elements(document, "header_field"):
        payload = dict(_active_payload(e))
        payload.pop("example_value", None)
        header_fields.append(payload)
    if header_fields:
        recipe["header_fields"] = header_fields
    return recipe


def _verify_profile(
    session: Session, proposal: Proposal, recipe: dict
) -> dict:
    """Run every FR-022/FR-024 check; return the full report (ok + checks)."""
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    document = proposal.document
    confirmed_columns = [
        _active_payload(e)["name"] for e in _elements(document, "record_column")
    ]
    table_elements = _elements(document, "record_table")
    expected_rows = (
        table_elements[0]["evidence"].get("recurrence") if table_elements else None
    )
    confirmed_headers = {
        _active_payload(e)["name"]: e["payload"].get("example_value")
        for e in _elements(document, "header_field")
        if e["review_state"] == "confirmed"
    }

    for i, sha in enumerate(proposal.row.exemplar_shas):
        pdf_path = store.get_path(sha)
        normalized = extract(pdf_path, recipe)
        tag = f"exemplar[{i}]"

        check(
            f"{tag} fingerprint_self_match",
            matches_fingerprint(pdf_path, recipe["fingerprint"]),
            "recipe fingerprint must match its own exemplar",
        )
        missing = normalized["integrity"]["anchors_missing"]
        check(
            f"{tag} anchors", not missing,
            f"missing anchors: {missing}" if missing else "all anchors found",
        )

        findings = normalized["findings"]
        check(f"{tag} records_extracted", bool(findings), f"{len(findings)} records")
        if findings:
            keys = set(findings[0])
            absent = [c for c in confirmed_columns if c not in keys]
            check(
                f"{tag} columns_reproduced",
                not absent,
                f"columns missing from extraction: {absent}"
                if absent else "all confirmed columns present",
            )
        if i == 0 and expected_rows is not None:
            check(
                f"{tag} row_count_exact",
                len(findings) == expected_rows,
                f"expected {expected_rows} rows (analyst-reviewed), extracted {len(findings)}",
            )
        if i == 0:
            for name, example in confirmed_headers.items():
                if example:
                    got = normalized["header"].get(name, "")
                    check(
                        f"{tag} header_{name}_exact",
                        got == example,
                        f"confirmed {example!r}, extracted {got!r}",
                    )

    # FR-024: no active registered profile may also claim this shape
    primary_path = store.get_path(proposal.row.exemplar_shas[0])
    colliding = [
        f"{p.key}@{p.structural_version}"
        for p in session.scalars(select(SourceProfile).where(SourceProfile.status == "active"))
        if matches_fingerprint(primary_path, p.fingerprint)
    ]
    check(
        "fingerprint_no_collision",
        not colliding,
        f"existing profile(s) also match this exemplar: {colliding}" if colliding
        else "no active profile matches",
    )

    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def approve_profile(
    session: Session, proposal: Proposal, key: str, version: str, operator: str
) -> SourceProfile:
    """The only path from draft profile proposal to registered SourceProfile."""
    proposal.ensure_approvable()  # FR-003: nothing unresolved
    recipe = recipe_from_elements(proposal.document, key, version)
    validate_recipe(recipe)  # Constitution IV: schema-validated data

    report = _verify_profile(session, proposal, recipe)
    if not report["ok"]:
        proposal.record_verify_failure(report)
        raise VerifyFailure(report)

    recipe_path = profiles_root() / f"{key}.{version}.yaml"
    recipe_path.write_text(yaml.safe_dump(recipe, sort_keys=True))

    row = SourceProfile(
        key=key,
        structural_version=version,
        platform=recipe["platform"],
        export_kind="pdf",
        job_type=recipe["job_type"],
        fingerprint=recipe["fingerprint"],
        extractor_ref="rmu.extract.recipe_pdf",
        declared_totals_fields={},
        status="active",
        effective_from=datetime.date.today(),
    )
    session.add(row)
    session.flush()
    proposal.mark_approved(operator, verify_report=report, resulting_profile_id=row.id)
    return row
