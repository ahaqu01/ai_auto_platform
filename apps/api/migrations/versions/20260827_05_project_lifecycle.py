"""M1-07 project lifecycle, membership and optimistic versioning."""

import sqlalchemy as sa
from alembic import op

revision = "20260827_05"
down_revision = "20260827_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "projects",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "projects", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "projects", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_projects_organization_status_updated",
        "projects",
        ["organization_id", "status", sa.text("updated_at DESC")],
    )
    op.create_table(
        "project_members",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
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
            "role in ('ADMIN', 'ENGINEER', 'VIEWER')",
            name="ck_project_members_role",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_project_members_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_members_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_project_members_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("project_id", "user_id", name="pk_project_members"),
    )
    op.create_index(
        "ix_project_members_organization_id",
        "project_members",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_table("project_members")
    op.drop_index("ix_projects_organization_status_updated", table_name="projects")
    op.drop_column("projects", "deleted_at")
    op.drop_column("projects", "archived_at")
    op.drop_column("projects", "version")
    op.drop_column("projects", "description")
