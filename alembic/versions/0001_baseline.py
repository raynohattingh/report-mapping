"""Baseline: all 8 tables per data-model.md. Additive-only (Constitution III).

Revision ID: 0001
Revises: None
"""

from alembic import op

from rmu.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Baseline creates the full v1 schema from the model metadata. Later
    # revisions must use explicit additive ops only; the invariant test
    # tests/invariants/test_append_only.py walks versions for destructive ops.
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    raise NotImplementedError("append-only registries: no destructive downgrade (Constitution III)")
