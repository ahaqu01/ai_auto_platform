"""add stable OIDC identity columns"""

import sqlalchemy as sa
from alembic import op

revision = "20260821_02"
down_revision = "20260820_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("external_issuer", sa.String(500), nullable=True))
    op.add_column("users", sa.Column("external_subject", sa.String(255), nullable=True))
    op.create_unique_constraint(
        "uq_users_external_identity",
        "users",
        ["external_issuer", "external_subject"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_users_external_identity", "users", type_="unique")
    op.drop_column("users", "external_subject")
    op.drop_column("users", "external_issuer")
