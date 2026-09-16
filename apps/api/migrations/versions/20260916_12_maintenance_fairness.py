"""Persist fair artifact and orphan reconciliation progress."""

import sqlalchemy as sa
from alembic import op

revision = "20260916_12"
down_revision = "20260915_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "artifacts",
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_artifacts_last_reconciled_at", "artifacts", ["last_reconciled_at"]
    )
    op.create_table(
        "artifact_maintenance_state",
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value", sa.String(512), nullable=True),
        sa.PrimaryKeyConstraint("key", name="pk_artifact_maintenance_state"),
    )


def downgrade() -> None:
    op.drop_table("artifact_maintenance_state")
    op.drop_index("ix_artifacts_last_reconciled_at", table_name="artifacts")
    op.drop_column("artifacts", "last_reconciled_at")
