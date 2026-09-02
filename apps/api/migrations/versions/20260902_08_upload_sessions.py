"""M2-03 upload session metadata, quota reservation and RLS."""

import sqlalchemy as sa
from alembic import op

revision = "20260902_08"
down_revision = "20260827_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(512), nullable=False),
        sa.Column("object_key", sa.String(64), nullable=False),
        sa.Column("expected_size", sa.BigInteger(), nullable=False),
        sa.Column("expected_sha256", sa.String(64), nullable=False),
        sa.Column("declared_content_type", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), server_default="PENDING_UPLOAD", nullable=False),
        sa.Column("storage_upload_id", sa.String(512), nullable=True),
        sa.Column("reserved_bytes", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("expected_size > 0 AND expected_size <= 21474836480", name="ck_upload_sessions_expected_size"),
        sa.CheckConstraint("expected_sha256 = lower(expected_sha256) AND length(expected_sha256) = 64", name="ck_upload_sessions_expected_sha256"),
        sa.CheckConstraint("reserved_bytes >= 0", name="ck_upload_sessions_reserved_bytes"),
        sa.CheckConstraint("status in ('PENDING_UPLOAD','UPLOADING','COMPLETING','COMPLETED','ABORTED','EXPIRED','FAILED')", name="ck_upload_sessions_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_upload_sessions"),
        sa.UniqueConstraint("object_key", name="uq_upload_sessions_object_key"),
    )
    op.create_index("ix_upload_sessions_organization_id", "upload_sessions", ["organization_id"])
    op.create_index("ix_upload_sessions_project_id", "upload_sessions", ["project_id"])
    op.create_index("ix_upload_sessions_expires_at", "upload_sessions", ["expires_at"])
    op.create_index(
        "ix_upload_sessions_active_org",
        "upload_sessions",
        ["organization_id", "expires_at"],
        postgresql_where=sa.text("status in ('PENDING_UPLOAD','UPLOADING','COMPLETING')"),
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE upload_sessions TO platform_runtime")
    op.execute("ALTER TABLE upload_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE upload_sessions FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON upload_sessions "
        "USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid) "
        "WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON upload_sessions")
    op.execute("ALTER TABLE upload_sessions DISABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON TABLE upload_sessions FROM platform_runtime")
    op.drop_table("upload_sessions")
