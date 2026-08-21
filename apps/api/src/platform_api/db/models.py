from __future__ import annotations

from uuid import UUID

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_api.db.base import Base, IdMixin, TimestampMixin
from platform_api.modules.organization.domain import OrganizationRole
from platform_api.modules.project.domain import ProjectStatus


class UserModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint(
            "external_issuer", "external_subject", name="uq_users_external_identity"
        ),
    )

    external_issuer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
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


class ProjectModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, native_enum=False, length=16),
        default=ProjectStatus.ACTIVE,
        nullable=False,
    )
