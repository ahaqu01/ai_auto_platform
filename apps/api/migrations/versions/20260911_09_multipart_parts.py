"""M2-04 multipart part registration and tenant RLS."""

import sqlalchemy as sa
from alembic import op

revision = "20260911_09"
down_revision = "20260902_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "upload_parts",
        sa.Column("upload_session_id", sa.Uuid(), nullable=False),
        sa.Column("part_number", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("etag", sa.String(512), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
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
        sa.CheckConstraint(
            "part_number >= 1 AND part_number <= 10000", name="ck_upload_parts_number"
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_upload_parts_size"),
        sa.ForeignKeyConstraint(
            ["upload_session_id"], ["upload_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint(
            "upload_session_id", "part_number", name="pk_upload_parts"
        ),
    )
    op.create_index(
        "ix_upload_parts_organization_id", "upload_parts", ["organization_id"]
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE upload_parts TO platform_runtime"
    )
    op.execute("ALTER TABLE upload_parts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE upload_parts FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON upload_parts "
        "USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid) "
        "WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON upload_parts")
    op.execute("ALTER TABLE upload_parts DISABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON TABLE upload_parts FROM platform_runtime")
    op.drop_table("upload_parts")
