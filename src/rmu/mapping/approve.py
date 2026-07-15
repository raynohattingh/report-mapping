"""FR-007 approval gate: nothing unreviewed or unrouted enters an approved
transform (Constitution V — T2 proposals never survive approval)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from rmu.mapping import loader


class ApprovalRefused(RuntimeError):
    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("; ".join(reasons))


def check_approval(doc: dict, required_fields: list[str], session: Session) -> None:
    reasons: list[str] = []
    missing = loader.missing_required(doc, required_fields)
    if missing:
        reasons.append(f"required target fields unrouted: {', '.join(missing)}")
    for field in loader.unreviewed_fields(doc):
        tier = doc["routes"][field]["tier"]
        reasons.append(f"field '{field}' still at tier {tier} (needs an explicit human decision)")
    reasons.extend(loader.unresolved_value_maps(doc, session))
    if reasons:
        raise ApprovalRefused(sorted(reasons))


def gate_state(doc: dict, required_fields: list[str], session: Session) -> dict:
    """The approval gate as inspectable state (FR-019 readiness bar).

    NEVER a parallel calculation: composed of the same loader checks
    check_approval raises on, so the bar and the gate cannot disagree."""
    routed = loader.routed_fields(doc)
    missing = loader.missing_required(doc, required_fields)
    pending = [f for f in loader.unreviewed_fields(doc)
               if doc["routes"][f]["tier"] == "T2"]
    unmapped_routes = [f for f in loader.unreviewed_fields(doc)
                       if doc["routes"][f]["tier"] == "T3"]
    unresolved_pins = loader.unresolved_value_maps(doc, session)
    blockers = sorted(set(missing) | set(pending) | set(unmapped_routes))
    return {
        "total_required": len(required_fields),
        "routed": len(routed),
        "ready": len([f for f in required_fields
                      if f in routed and f not in blockers]),
        "t2_pending": pending,
        "t3_unmapped": sorted(set(missing) | set(unmapped_routes)),
        "unresolved_value_maps": unresolved_pins,
        "approvable": not (missing or pending or unmapped_routes or unresolved_pins),
        "next_blocking": (pending + sorted(set(missing) | set(unmapped_routes)))[:1],
    }


def approve_session(s: Session, session_id: int, by: str):
    """The full `rmu map approve` body: gate → versioned Transform → decisions.

    Extracted for feature 004 (research.md R4) so CLI and studio approvals
    store the same row. Raises TransformValidationError / ApprovalRefused with
    the same content the CLI printed; a terminal session refuses (racing
    approvals across surfaces can never double-register)."""
    import datetime

    from sqlalchemy import func, select

    from rmu.mapping.loader import parse_transform
    from rmu.mapping.session import compute_decisions
    from rmu.mapping.start import StartRefused, load_session_state
    from rmu.models import Transform
    from rmu.registry import get_template_by_id, required_fields

    ms, draft_path, _doc_row = load_session_state(s, session_id)
    if ms.status != "draft":
        raise StartRefused(
            f"refused: session {session_id} is {ms.status} (terminal)", 3)
    template_row = get_template_by_id(s, ms.target_template_id)
    text = draft_path.read_text(encoding="utf-8")
    doc = parse_transform(text)
    check_approval(doc, required_fields(template_row), s)

    current = s.scalar(
        select(func.max(Transform.version)).where(
            Transform.source_profile_id == ms.source_profile_id,
            Transform.target_template_id == ms.target_template_id,
        )
    )
    version = (current or 0) + 1
    transform = Transform(
        source_profile_id=ms.source_profile_id,
        target_template_id=ms.target_template_id,
        version=version,
        effective_from=datetime.date.today(),
        yaml_body=text,
        approved_by=by,
        approved_at=datetime.datetime.now(datetime.UTC),
        parent_version=current,
    )
    s.add(transform)
    s.flush()
    ms.decisions = compute_decisions(ms.proposals, doc)
    ms.status = "approved"
    ms.resulting_transform_id = transform.id
    s.commit()
    return transform, ms
