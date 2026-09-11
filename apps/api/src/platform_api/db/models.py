from __future__ import annotations

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_api.db.base import Base, IdMixin, TimestampMixin
from platform_api.modules.artifact.domain import UploadSessionStatus
from platform_api.modules.organization.domain import OrganizationRole
from platform_api.modules.project.domain import ProjectRole, ProjectStatus


class UserModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint(
            "external_issuer", "external_subject", name="uq_users_external_identity"
        ),
    )

    external_issuer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)


class OrganizationModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    members: Mapped[list[OrganizationMemberModel]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class OrganizationMemberModel(TimestampMixin, Base):
    __tablename__ = "organization_members"
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[OrganizationRole] = mapped_column(
        Enum(OrganizationRole, native_enum=False, length=16), nullable=False
    )
    organization: Mapped[OrganizationModel] = relationship(back_populates="members")


class OrganizationInviteModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "organization_invites"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_organization_invites_token_hash"),
        UniqueConstraint(
            "organization_id",
            "email",
            name="uq_organization_invites_organization_email",
        ),
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[OrganizationRole] = mapped_column(
        Enum(OrganizationRole, native_enum=False, length=16), nullable=False
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    invited_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, native_enum=False, length=16),
        default=ProjectStatus.ACTIVE,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __mapper_args__: ClassVar[dict[str, object]] = dict(version_id_col=version)  # noqa: C408


class ProjectMemberModel(TimestampMixin, Base):
    __tablename__ = "project_members"
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[ProjectRole] = mapped_column(
        Enum(ProjectRole, native_enum=False, length=16), nullable=False
    )


class UploadSessionModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "upload_sessions"
    __table_args__ = (
        UniqueConstraint("object_key", name="uq_upload_sessions_object_key"),
        CheckConstraint(
            "expected_size > 0 AND expected_size <= 21474836480",
            name="ck_upload_sessions_expected_size",
        ),
        CheckConstraint(
            "expected_sha256 = lower(expected_sha256) AND length(expected_sha256) = 64",
            name="ck_upload_sessions_expected_sha256",
        ),
        CheckConstraint(
            "reserved_bytes >= 0", name="ck_upload_sessions_reserved_bytes"
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    object_key: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    declared_content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[UploadSessionStatus] = mapped_column(
        Enum(UploadSessionStatus, native_enum=False, length=24),
        default=UploadSessionStatus.PENDING_UPLOAD,
        nullable=False,
    )
    storage_upload_id: Mapped[str | None] = mapped_column(String(512))
    reserved_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    __mapper_args__: ClassVar[dict[str, object]] = dict(version_id_col=version)  # noqa: C408


class UploadPartModel(TimestampMixin, Base):
    __tablename__ = "upload_parts"
    __table_args__ = (
        CheckConstraint(
            "part_number >= 1 AND part_number <= 10000", name="ck_upload_parts_number"
        ),
        CheckConstraint("size_bytes > 0", name="ck_upload_parts_size"),
    )
    upload_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("upload_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    part_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    etag: Mapped[str] = mapped_column(String(512), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)


class AuditEventModel(IdMixin, Base):
    __tablename__ = "audit_events"

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    organization_id: Mapped[UUID | None] = mapped_column(index=True)
    project_id: Mapped[UUID | None] = mapped_column()
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict[str, object]] = mapped_column(
        JSON, default=dict, nullable=False
    )


class IdempotencyRecordModel(TimestampMixin, Base):
    __tablename__ = "idempotency_records"

    actor_id: Mapped[UUID] = mapped_column(primary_key=True)
    route_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, object] | None] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )


class OutboxEventModel(IdMixin, Base):
    __tablename__ = "outbox_events"

    organization_id: Mapped[UUID | None] = mapped_column(index=True)
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
