"""M1-08 audit, idempotency and transactional outbox baseline."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260827_06"
down_revision = "20260827_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "detail",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "actor_type in ('USER', 'AGENT', 'SYSTEM')",
            name="ck_audit_events_actor_type",
        ),
        sa.CheckConstraint(
            "result in ('SUCCESS', 'DENIED', 'FAILED')", name="ck_audit_events_result"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index(
        "ix_audit_events_org_occurred",
        "audit_events",
        ["organization_id", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_audit_events_resource", "audit_events", ["resource_type", "resource_id"]
    )

    op.create_table(
        "idempotency_records",
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("route_key", sa.String(160), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column(
            "response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
            "state in ('PROCESSING', 'COMPLETED')", name="ck_idempotency_records_state"
        ),
        sa.PrimaryKeyConstraint(
            "actor_id", "route_key", "idempotency_key", name="pk_idempotency_records"
        ),
    )
    op.create_index(
        "ix_idempotency_records_expires_at", "idempotency_records", ["expires_at"]
    )

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("aggregate_type", sa.String(50), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_outbox_events"),
    )
    op.create_index(
        "ix_outbox_events_unpublished",
        "outbox_events",
        ["occurred_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_index(
        "ix_outbox_events_aggregate",
        "outbox_events",
        ["aggregate_type", "aggregate_id"],
    )


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("idempotency_records")
    op.drop_table("audit_events")
