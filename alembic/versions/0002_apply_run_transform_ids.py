"""Add apply_runs.transform_ids for multi-template runs (convergence T051).

Additive only (Constitution III). Guarded against fresh databases whose 0001
create_all baseline already includes the column.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = [c["name"] for c in sa.inspect(bind).get_columns("apply_runs")]
    if "transform_ids" not in columns:
        op.add_column("apply_runs", sa.Column("transform_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    raise NotImplementedError("append-only registries: no destructive downgrade (Constitution III)")
