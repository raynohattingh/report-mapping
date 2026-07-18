"""Onboarding proposal lifecycle (feature 003, D5).

A proposal is working state: a schema-validated document (see
schemas/proposal.schema.json) persisted twice — as the DB row's `document`
JSON and as an analyst-editable YAML in store/drafts (D1 pattern). The YAML is
the analyst's editing surface; `Proposal.load` syncs it back. Only two
transitions exist: draft→approved (via the verify gate in approve.py) and
draft→abandoned. Draft rows are never registry rows (FR-016).
"""

from __future__ import annotations

import datetime
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from rmu.models import OnboardingProposal
from rmu.onboard.schemas import validate_proposal
from rmu.store import drafts_dir


class ProposalStateError(RuntimeError):
    """Illegal lifecycle transition (approved/abandoned are terminal)."""


class UnresolvedElementsError(ProposalStateError):
    """Approval attempted while elements are still 'proposed' (FR-003)."""

    def __init__(self, element_ids: list[str]):
        self.element_ids = element_ids
        super().__init__(
            "approval blocked - unresolved elements (confirm/correct/remove each): "
            + ", ".join(element_ids)
        )


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class Proposal:
    """Wrapper over an OnboardingProposal row + its draft YAML."""

    def __init__(self, session: Session, row: OnboardingProposal):
        self._session = session
        self.row = row

    # -- construction -------------------------------------------------------

    @classmethod
    def create(
        cls,
        session: Session,
        document: dict,
        *,
        diagnosis: dict | None = None,
        ai_assist: dict | None = None,
        seeded_from_profile_id: int | None = None,
    ) -> Proposal:
        validate_proposal(document)
        row = OnboardingProposal(
            kind=document["kind"],
            status="draft",
            exemplar_shas=document["exemplars"],
            document=document,
            diagnosis=diagnosis or document.get("diagnosis"),
            ai_assist=ai_assist or document.get("ai_assist"),
            seeded_from_profile_id=seeded_from_profile_id,
            created_at=_now(),
        )
        session.add(row)
        session.flush()  # assign id before naming the draft file
        proposal = cls(session, row)
        row.draft_ref = proposal.save_draft()
        session.commit()
        return proposal

    @classmethod
    def load(cls, session: Session, proposal_id: int, *, sync: bool = True) -> Proposal:
        row = session.get(OnboardingProposal, proposal_id)
        if row is None:
            raise ProposalStateError(f"no onboarding proposal #{proposal_id}")
        proposal = cls(session, row)
        if sync and row.status == "draft" and proposal.draft_path().exists():
            edited = yaml.safe_load(proposal.draft_path().read_text())
            validate_proposal(edited)
            if edited != row.document:
                row.document = edited
                session.commit()
        return proposal

    # -- accessors -----------------------------------------------------------

    @property
    def id(self) -> int:
        return self.row.id

    @property
    def kind(self) -> str:
        return self.row.kind

    @property
    def status(self) -> str:
        return self.row.status

    @property
    def document(self) -> dict:
        return self.row.document

    @property
    def elements(self) -> list[dict]:
        return self.row.document.get("elements", [])

    def draft_path(self) -> Path:
        return drafts_dir() / f"onboard_{self.row.id}.yaml"

    # -- draft editing surface ------------------------------------------------

    def save_draft(self) -> str:
        path = self.draft_path()
        path.write_text(yaml.safe_dump(self.row.document, sort_keys=True, allow_unicode=True))
        return path.name

    def unresolved(self) -> list[str]:
        return [e["id"] for e in self.elements if e["review_state"] == "proposed"]

    # -- element review edits (shared by CLI hand-editing and the studio) -----
    #
    # These write exactly the review_state / corrected_payload a YAML hand-edit
    # writes, then persist through save_draft()+commit so CLI review stays
    # interchangeable mid-proposal (feature 004, FR-033).

    def _write_document(self, document: dict) -> None:
        validate_proposal(document)
        self.row.document = document  # reassign so SQLAlchemy sees the JSON change
        self.save_draft()
        self._session.commit()

    def _element(self, document: dict, element_id: str) -> dict:
        for e in document.get("elements", []):
            if e["id"] == element_id:
                return e
        raise ProposalStateError(f"no element {element_id!r} in proposal #{self.row.id}")

    def set_review_state(
        self, element_id: str, state: str,
        corrected_payload: dict | None = None,
    ) -> None:
        """confirm / correct / remove one element (FR-033)."""
        self._require_draft("review element of")
        if state not in ("proposed", "confirmed", "corrected", "removed"):
            raise ProposalStateError(f"invalid review_state {state!r}")
        document = dict(self.row.document)
        document["elements"] = [dict(e) for e in document.get("elements", [])]
        element = self._element(document, element_id)
        element["review_state"] = state
        if state == "corrected":
            if corrected_payload is None:
                raise ProposalStateError("correction needs a corrected_payload")
            element["corrected_payload"] = corrected_payload
        else:
            element.pop("corrected_payload", None)
        self._write_document(document)

    def add_element(self, element: dict) -> str:
        """Add an analyst-sourced element the detector missed (FR-033a).

        Passes through the same review lifecycle and verify-on-approve as
        detected elements; evidence.source is forced to 'analyst'."""
        self._require_draft("add an element to")
        document = dict(self.row.document)
        elements = [dict(e) for e in document.get("elements", [])]
        existing = {e["id"] for e in elements}
        base = element.get("id") or f"analyst_{element['element_kind']}"
        eid = base
        n = 1
        while eid in existing:
            n += 1
            eid = f"{base}_{n}"
        new = {
            "id": eid,
            "element_kind": element["element_kind"],
            "confidence": element.get("confidence", 1.0),
            "evidence": {**element.get("evidence", {}), "source": "analyst"},
            "review_state": element.get("review_state", "confirmed"),
            "payload": element["payload"],
        }
        if new["review_state"] == "corrected":
            new["corrected_payload"] = element.get("corrected_payload", element["payload"])
        elements.append(new)
        document["elements"] = elements
        self._write_document(document)
        return eid

    def bulk_confirm_page(self, page: int) -> list[str]:
        """Confirm every still-'proposed' element on a page (FR-034).

        Recorded per element — indistinguishable from confirming each one."""
        self._require_draft("bulk-confirm elements of")
        document = dict(self.row.document)
        elements = [dict(e) for e in document.get("elements", [])]
        confirmed: list[str] = []
        for e in elements:
            if e["review_state"] != "proposed":
                continue
            pages = e.get("evidence", {}).get("pages") or [e.get("payload", {}).get("page")]
            if page in pages:
                e["review_state"] = "confirmed"
                confirmed.append(e["id"])
        document["elements"] = elements
        self._write_document(document)
        return confirmed

    # -- lifecycle -------------------------------------------------------------

    def _require_draft(self, action: str) -> None:
        if self.row.status != "draft":
            raise ProposalStateError(
                f"cannot {action}: proposal #{self.row.id} is {self.row.status} (terminal)"
            )

    def ensure_approvable(self) -> None:
        self._require_draft("approve")
        pending = self.unresolved()
        if pending:
            raise UnresolvedElementsError(pending)

    def mark_approved(
        self,
        by: str,
        *,
        verify_report: dict,
        resulting_profile_id: int | None = None,
        resulting_template_id: int | None = None,
    ) -> None:
        self._require_draft("approve")
        self.row.status = "approved"
        self.row.approved_by = by  # FR-017: who
        self.row.approved_at = _now()  # FR-017: when
        self.row.verify_report = verify_report
        self.row.resulting_profile_id = resulting_profile_id
        self.row.resulting_template_id = resulting_template_id
        self._session.commit()

    def mark_abandoned(self) -> None:
        self._require_draft("abandon")
        self.row.status = "abandoned"
        self._session.commit()

    def record_verify_failure(self, report: dict) -> None:
        """Verify-on-approve failed: stay draft, keep the evidence (FR-022)."""
        self._require_draft("record verify failure on")
        self.row.verify_report = report
        self._session.commit()
