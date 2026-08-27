"""make user email non-unique

Revision ID: 20260827_03
Revises: 20260821_02
"""

from alembic import op

revision = "20260827_03"
down_revision = "20260821_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_users_email", "users", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint("uq_users_email", "users", ["email"])
