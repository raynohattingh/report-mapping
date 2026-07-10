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
