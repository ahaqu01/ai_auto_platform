"""add organization invitations

Revision ID: 20260827_04
Revises: 20260827_03
"""

import sqlalchemy as sa
from alembic import op

revision = "20260827_04"
down_revision = "20260827_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_invites",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("invited_by", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_invites_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by"],
            ["users.id"],
            name="fk_organization_invites_invited_by_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organization_invites"),
        sa.UniqueConstraint("token_hash", name="uq_organization_invites_token_hash"),
        sa.UniqueConstraint(
            "organization_id",
            "email",
            name="uq_organization_invites_organization_email",
        ),
    )


def downgrade() -> None:
    op.drop_table("organization_invites")
