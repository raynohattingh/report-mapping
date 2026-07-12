"""Create onboarding_proposals for feature 003 (D5, data-model.md).

Additive only (Constitution III): a NEW working-state table, not an append-only
registry; no existing table or row is touched. Guarded against fresh databases
whose 0001 create_all baseline already includes the table.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("onboarding_proposals"):
        return
    op.create_table(
        "onboarding_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("exemplar_shas", sa.JSON(), nullable=False),
        sa.Column(
            "seeded_from_profile_id",
            sa.Integer(),
            sa.ForeignKey("source_profiles.id"),
            nullable=True,
        ),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("diagnosis", sa.JSON(), nullable=True),
        sa.Column("draft_ref", sa.String(64), nullable=True),
        sa.Column("ai_assist", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_by", sa.String(80), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("verify_report", sa.JSON(), nullable=True),
        sa.Column(
            "resulting_profile_id",
            sa.Integer(),
            sa.ForeignKey("source_profiles.id"),
            nullable=True,
        ),
        sa.Column(
            "resulting_template_id",
            sa.Integer(),
            sa.ForeignKey("target_templates.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    raise NotImplementedError(
        "append-only discipline: no destructive downgrade (Constitution III)"
    )
