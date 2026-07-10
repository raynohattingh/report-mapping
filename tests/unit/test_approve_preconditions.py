"""T017 [TDD]: FR-007 approval preconditions (design §7).

Approval is refused while: any required target field is unrouted, any tier is
T2 (unreviewed AI proposal) or T3 (unmapped), or a value-map pin is unresolved.
"""

import datetime

import pytest

from rmu.db import make_engine, make_session_factory
from rmu.mapping.approve import ApprovalRefused, check_approval
from rmu.mapping.loader import parse_transform
from rmu.models import Base, ValueMap

REQUIRED = ["finding_id", "priority"]

COMPLETE = """
meta:
  source_profile: scopito.pdf.powerline@v2020
  target_template: interim.defect_csv@1
  version: 1
routes:
  finding_id: {from: finding.id, tier: T0}
  priority:
    from: finding.severity
    tier: T1
    value_map: {name: severity_to_priority, version: 1}
"""


@pytest.fixture()
def session():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as s:
        s.add(ValueMap(name="severity_to_priority", version=1,
                       entries=[{"source_value": "5", "target_value": "P1",
                                 "provenance": "human"}],
                       effective_from=datetime.date(2026, 7, 11)))
        s.commit()
        yield s


def test_complete_draft_approves(session):
    check_approval(parse_transform(COMPLETE), REQUIRED, session)  # must not raise


def test_missing_required_field_refused(session):
    doc = parse_transform(COMPLETE)
    del doc["routes"]["priority"]
    with pytest.raises(ApprovalRefused, match="priority"):
        check_approval(doc, REQUIRED, session)


def test_unreviewed_T2_proposal_refused(session):
    doc = parse_transform(COMPLETE.replace("tier: T1", "tier: T2"))
    with pytest.raises(ApprovalRefused, match="T2"):
        check_approval(doc, REQUIRED, session)


def test_unmapped_T3_refused(session):
    doc = parse_transform(COMPLETE.replace("tier: T1", "tier: T3"))
    with pytest.raises(ApprovalRefused, match="T3"):
        check_approval(doc, REQUIRED, session)


def test_unresolved_value_map_pin_refused(session):
    doc = parse_transform(COMPLETE.replace("version: 1}", "version: 9}"))
    with pytest.raises(ApprovalRefused, match="severity_to_priority@9"):
        check_approval(doc, REQUIRED, session)
