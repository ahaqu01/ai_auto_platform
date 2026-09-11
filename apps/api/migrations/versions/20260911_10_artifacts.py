"""M2-05 verified asset lifecycle and tenant RLS."""

import sqlalchemy as sa
from alembic import op

revision = "20260911_10"
down_revision = "20260911_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("upload_session_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(512), nullable=False),
        sa.Column("object_key", sa.String(64), nullable=False),
        sa.Column("bucket_alias", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("expected_sha256", sa.String(64), nullable=False),
        sa.Column("verified_sha256", sa.String(64), nullable=False),
        sa.Column("declared_content_type", sa.String(255), nullable=False),
        sa.Column("detected_content_type", sa.String(255), nullable=True),
        sa.Column("integrity_status", sa.String(24), nullable=False),
        sa.Column("security_scan_status", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
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
        sa.CheckConstraint("size_bytes >= 0", name="ck_artifacts_size"),
        sa.CheckConstraint(
            "length(expected_sha256) = 64 AND length(verified_sha256) = 64",
            name="ck_artifacts_sha256",
        ),
        sa.CheckConstraint(
            "integrity_status in ('VERIFIED','MISMATCH')",
            name="ck_artifacts_integrity_status",
        ),
        sa.CheckConstraint(
            "security_scan_status in ('NOT_REQUIRED','PENDING','CLEAN','BLOCKED')",
            name="ck_artifacts_scan_status",
        ),
        sa.CheckConstraint(
            "status in ('VERIFYING','AVAILABLE','QUARANTINED','FAILED','DELETING','DELETED')",
            name="ck_artifacts_status",
        ),
        sa.ForeignKeyConstraint(
            ["upload_session_id"], ["upload_sessions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_artifacts"),
        sa.UniqueConstraint("upload_session_id", name="uq_artifacts_upload_session_id"),
        sa.UniqueConstraint("object_key", name="uq_artifacts_object_key"),
    )
    op.create_index("ix_artifacts_organization_id", "artifacts", ["organization_id"])
    op.create_index("ix_artifacts_project_id", "artifacts", ["project_id"])
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE artifacts TO platform_runtime"
    )
    op.execute("ALTER TABLE artifacts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE artifacts FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON artifacts "
        "USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid) "
        "WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON artifacts")
    op.execute("ALTER TABLE artifacts DISABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON TABLE artifacts FROM platform_runtime")
    op.drop_table("artifacts")
