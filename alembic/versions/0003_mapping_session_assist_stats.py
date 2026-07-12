"""Add mapping_sessions.assist_stats for local AI assistance (feature 002).

Additive only (Constitution III): mapping_sessions is NOT an append-only
registry, and the column is nullable (NULL = pre-002 session, data-model §1).
Guarded against fresh databases whose 0001 create_all baseline already includes
the column.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = [c["name"] for c in sa.inspect(bind).get_columns("mapping_sessions")]
    if "assist_stats" not in columns:
        op.add_column("mapping_sessions", sa.Column("assist_stats", sa.JSON(), nullable=True))


def downgrade() -> None:
    raise NotImplementedError(
        "append-only discipline: no destructive downgrade (Constitution III)"
    )
