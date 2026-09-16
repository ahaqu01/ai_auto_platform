"""M2-07 artifact cleanup retry and deletion state."""

import sqlalchemy as sa
from alembic import op

revision = "20260915_11"
down_revision = "20260911_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("upload_sessions", "artifacts"):
        op.add_column(
            table,
            sa.Column(
                "cleanup_attempts", sa.Integer(), server_default="0", nullable=False
            ),
        )
        op.add_column(
            table, sa.Column("cleanup_last_error", sa.String(64), nullable=True)
        )
        op.add_column(
            table,
            sa.Column(
                "cleanup_next_attempt_at", sa.DateTime(timezone=True), nullable=True
            ),
        )
        op.create_check_constraint(
            f"ck_{table}_cleanup_attempts", table, "cleanup_attempts >= 0"
        )
        op.create_index(
            f"ix_{table}_cleanup_next_attempt_at", table, ["cleanup_next_attempt_at"]
        )
    op.add_column(
        "artifacts", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("artifacts", "deleted_at")
    for table in ("artifacts", "upload_sessions"):
        op.drop_index(f"ix_{table}_cleanup_next_attempt_at", table_name=table)
        op.drop_constraint(f"ck_{table}_cleanup_attempts", table, type_="check")
        op.drop_column(table, "cleanup_next_attempt_at")
        op.drop_column(table, "cleanup_last_error")
        op.drop_column(table, "cleanup_attempts")
