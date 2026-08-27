import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_api.auth.dependencies import CurrentUser
from platform_api.common.api_contract import (
    PROTECTED_ERROR_RESPONSES,
    StrictModel,
    StrictOrmModel,
)
from platform_api.common.errors import DomainError
from platform_api.db.models import (
    OrganizationInviteModel,
    OrganizationMemberModel,
    OrganizationModel,
    UserModel,
)
from platform_api.db.session import get_session
from platform_api.modules.organization.domain import OrganizationRole

from .organization_access import (
    require_organization_admin,
    require_organization_member,
)

router = APIRouter(
    prefix="/api/v1/organizations",
    tags=["organizations"],
    responses=PROTECTED_ERROR_RESPONSES,
)
invite_router = APIRouter(
    prefix="/api/v1/invites",
    tags=["organization-invites"],
    responses=PROTECTED_ERROR_RESPONSES,
)
DbSession = Annotated[AsyncSession, Depends(get_session)]
InvitableRole = Literal[OrganizationRole.ADMIN, OrganizationRole.MEMBER]


class OrganizationCreate(StrictModel):
    name: str = Field(min_length=2, max_length=120)


class OrganizationRead(StrictOrmModel):
    id: UUID
    name: str


class InviteCreate(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    role: InvitableRole

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if (
            normalized.count("@") != 1
            or normalized.startswith("@")
            or normalized.endswith("@")
        ):
            raise ValueError("invalid email address")
        return normalized


class InviteRead(StrictModel):
    id: UUID
    organization_id: UUID
    email: str
    role: OrganizationRole
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None


class InviteCreated(InviteRead):
    token: str


class MemberRead(StrictModel):
    organization_id: UUID
    user_id: UUID
    email: str
    display_name: str
    role: OrganizationRole


class MemberRoleUpdate(StrictModel):
    role: InvitableRole


def _invite_read(invite: OrganizationInviteModel, token: str | None = None):
    values = {
        "id": invite.id,
        "organization_id": invite.organization_id,
        "email": invite.email,
        "role": invite.role,
        "expires_at": invite.expires_at,
        "accepted_at": invite.accepted_at,
        "revoked_at": invite.revoked_at,
    }
    return InviteCreated(**values, token=token) if token else InviteRead(**values)


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate, current_user: CurrentUser, session: DbSession
) -> OrganizationModel:
    organization = OrganizationModel(name=payload.name.strip())
    session.add(organization)
    await session.flush()
    session.add(
        OrganizationMemberModel(
            organization_id=organization.id,
            user_id=current_user.id,
            role=OrganizationRole.OWNER,
        )
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DomainError("ORGANIZATION_CONFLICT", "企业创建冲突", 409) from exc
    await session.refresh(organization)
    return organization


@router.get("", response_model=list[OrganizationRead])
async def list_organizations(
    current_user: CurrentUser, session: DbSession
) -> list[OrganizationModel]:
    result = await session.scalars(
        select(OrganizationModel)
        .join(OrganizationMemberModel)
        .where(OrganizationMemberModel.user_id == current_user.id)
        .order_by(OrganizationModel.created_at)
    )
    return list(result)


@router.post(
    "/{organization_id}/invites", response_model=InviteCreated, status_code=201
)
async def create_invite(
    organization_id: UUID,
    payload: InviteCreate,
    current_user: CurrentUser,
    session: DbSession,
) -> InviteCreated:
    await require_organization_admin(session, organization_id, current_user.id)
    email = str(payload.email).strip().casefold()
    existing_member = await session.scalar(
        select(OrganizationMemberModel)
        .join(UserModel)
        .where(
            OrganizationMemberModel.organization_id == organization_id,
            func.lower(UserModel.email) == email,
        )
    )
    if existing_member:
        raise DomainError("MEMBER_ALREADY_EXISTS", "用户已经是企业成员", 409)
    existing = await session.scalar(
        select(OrganizationInviteModel).where(
            OrganizationInviteModel.organization_id == organization_id,
            OrganizationInviteModel.email == email,
        )
    )
    now = datetime.now(UTC)
    if (
        existing
        and not existing.accepted_at
        and not existing.revoked_at
        and existing.expires_at > now
    ):
        raise DomainError("INVITE_ALREADY_EXISTS", "有效邀请已存在", 409)
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).digest()
    invite = existing or OrganizationInviteModel(
        organization_id=organization_id, email=email
    )
    invite.role = payload.role
    invite.token_hash = token_hash
    invite.invited_by = current_user.id
    invite.expires_at = now + timedelta(days=7)
    invite.accepted_at = None
    invite.revoked_at = None
    session.add(invite)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DomainError("INVITE_CONFLICT", "邀请创建冲突", 409) from exc
    await session.refresh(invite)
    return _invite_read(invite, token)


@router.get("/{organization_id}/invites", response_model=list[InviteRead])
async def list_invites(
    organization_id: UUID, current_user: CurrentUser, session: DbSession
) -> list[InviteRead]:
    await require_organization_admin(session, organization_id, current_user.id)
    invites = await session.scalars(
        select(OrganizationInviteModel)
        .where(OrganizationInviteModel.organization_id == organization_id)
        .order_by(OrganizationInviteModel.created_at)
    )
    return [_invite_read(invite) for invite in invites]


@router.delete("/{organization_id}/invites/{invite_id}", status_code=204)
async def revoke_invite(
    organization_id: UUID,
    invite_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
) -> Response:
    await require_organization_admin(session, organization_id, current_user.id)
    invite = await session.scalar(
        select(OrganizationInviteModel).where(
            OrganizationInviteModel.id == invite_id,
            OrganizationInviteModel.organization_id == organization_id,
        )
    )
    if not invite:
        raise DomainError("INVITE_NOT_FOUND", "邀请不存在", 404)
    if invite.accepted_at:
        raise DomainError("INVITE_ALREADY_ACCEPTED", "邀请已接受", 409)
    invite.revoked_at = datetime.now(UTC)
    await session.commit()
    return Response(status_code=204)


@invite_router.post("/{token}/accept", response_model=MemberRead, status_code=201)
async def accept_invite(
    token: str, current_user: CurrentUser, session: DbSession
) -> MemberRead:
    token_hash = hashlib.sha256(token.encode()).digest()
    invite = await session.scalar(
        select(OrganizationInviteModel)
        .where(OrganizationInviteModel.token_hash == token_hash)
        .with_for_update()
    )
    if not invite:
        raise DomainError("INVITE_NOT_FOUND", "邀请不存在", 404)
    now = datetime.now(UTC)
    if invite.accepted_at:
        raise DomainError("INVITE_ALREADY_ACCEPTED", "邀请已接受", 409)
    if invite.revoked_at:
        raise DomainError("INVITE_REVOKED", "邀请已撤销", 409)
    if invite.expires_at <= now:
        raise DomainError("INVITE_EXPIRED", "邀请已过期", 409)
    if current_user.email.casefold() != invite.email.casefold():
        raise DomainError("INVITE_EMAIL_MISMATCH", "当前身份邮箱与邀请不匹配", 403)
    membership = OrganizationMemberModel(
        organization_id=invite.organization_id,
        user_id=current_user.id,
        role=invite.role,
    )
    session.add(membership)
    invite.accepted_at = now
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DomainError("MEMBER_ALREADY_EXISTS", "用户已经是企业成员", 409) from exc
    return MemberRead(
        organization_id=membership.organization_id,
        user_id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        role=membership.role,
    )


@router.get("/{organization_id}/members", response_model=list[MemberRead])
async def list_members(
    organization_id: UUID, current_user: CurrentUser, session: DbSession
) -> list[MemberRead]:
    await require_organization_member(session, organization_id, current_user.id)
    rows = (
        await session.execute(
            select(OrganizationMemberModel, UserModel)
            .join(UserModel, UserModel.id == OrganizationMemberModel.user_id)
            .where(OrganizationMemberModel.organization_id == organization_id)
            .order_by(OrganizationMemberModel.created_at)
        )
    ).all()
    return [
        MemberRead(
            organization_id=member.organization_id,
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=member.role,
        )
        for member, user in rows
    ]


async def _manageable_member(
    session: AsyncSession, organization_id: UUID, user_id: UUID
) -> OrganizationMemberModel:
    target = await session.scalar(
        select(OrganizationMemberModel).where(
            OrganizationMemberModel.organization_id == organization_id,
            OrganizationMemberModel.user_id == user_id,
        )
    )
    if not target:
        raise DomainError("MEMBER_NOT_FOUND", "企业成员不存在", 404)
    if target.role is OrganizationRole.OWNER:
        raise DomainError(
            "OWNER_MANAGEMENT_DEFERRED", "所有者变更将在安全流程中处理", 403
        )
    return target


@router.patch("/{organization_id}/members/{member_id}", response_model=MemberRead)
async def update_member(
    organization_id: UUID,
    member_id: UUID,
    payload: MemberRoleUpdate,
    current_user: CurrentUser,
    session: DbSession,
) -> MemberRead:
    await require_organization_admin(session, organization_id, current_user.id)
    target = await _manageable_member(session, organization_id, member_id)
    target.role = payload.role
    user = await session.get(UserModel, member_id)
    await session.commit()
    return MemberRead(
        organization_id=organization_id,
        user_id=member_id,
        email=user.email,
        display_name=user.display_name,
        role=target.role,
    )


@router.delete("/{organization_id}/members/{member_id}", status_code=204)
async def remove_member(
    organization_id: UUID,
    member_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
) -> Response:
    await require_organization_admin(session, organization_id, current_user.id)
    target = await _manageable_member(session, organization_id, member_id)
    await session.delete(target)
    await session.commit()
    return Response(status_code=204)
