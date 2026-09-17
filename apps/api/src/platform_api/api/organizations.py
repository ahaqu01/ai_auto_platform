import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.responses import JSONResponse
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
from platform_api.common.reliability import (
    begin_idempotent_command,
    complete_idempotent_command,
    record_audit,
    record_outbox,
)
from platform_api.common.tenancy import resolve_invite_tenant, set_tenant_context
from platform_api.db.models import (
    OrganizationInviteModel,
    OrganizationMemberModel,
    OrganizationModel,
    UserModel,
)
from platform_api.db.session import get_session
from platform_api.modules.organization.domain import OrganizationRole

from .organization_access import (
    change_member_role,
    remove_organization_member,
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
    role: OrganizationRole


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


def _record_organization_change(
    session: AsyncSession,
    request: Request,
    *,
    actor_id: UUID,
    organization_id: UUID,
    action: str,
    resource_type: str,
    resource_id: UUID,
    event_type: str,
    payload: dict[str, str],
) -> None:
    trace_id = getattr(request.state, "trace_id", None)
    record_audit(
        session,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        organization_id=organization_id,
        trace_id=trace_id,
        detail=payload,
    )
    record_outbox(
        session,
        organization_id=organization_id,
        aggregate_type="organization",
        aggregate_id=organization_id,
        event_type=event_type,
        aggregate_version=1,
        trace_id=trace_id,
        payload=payload,
    )


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate,
    current_user: CurrentUser,
    session: DbSession,
    request: Request,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> OrganizationModel | JSONResponse:
    decision = await begin_idempotent_command(
        session,
        actor_id=current_user.id,
        route_key="organizations.create",
        idempotency_key=idempotency_key,
        request_payload=payload.model_dump(mode="json"),
    )
    if decision.is_replay:
        return JSONResponse(
            status_code=decision.replay_status,
            content=decision.replay_body,
            headers={"Idempotent-Replayed": "true"},
        )
    organization = OrganizationModel(id=uuid4(), name=payload.name.strip())
    await set_tenant_context(session, organization.id, current_user.id)
    session.add(organization)
    await session.flush()
    session.add(
        OrganizationMemberModel(
            organization_id=organization.id,
            user_id=current_user.id,
            role=OrganizationRole.OWNER,
        )
    )
    trace_id = getattr(request.state, "trace_id", None)
    record_audit(
        session,
        actor_id=current_user.id,
        action="organization.create",
        resource_type="organization",
        resource_id=organization.id,
        organization_id=organization.id,
        trace_id=trace_id,
        detail={"name": organization.name},
    )
    record_outbox(
        session,
        organization_id=organization.id,
        aggregate_type="organization",
        aggregate_id=organization.id,
        event_type="OrganizationCreated.v1",
        aggregate_version=1,
        trace_id=trace_id,
        payload={"name": organization.name},
    )
    body = OrganizationRead.model_validate(organization).model_dump(mode="json")
    complete_idempotent_command(decision, response_status=201, response_body=body)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DomainError("ORGANIZATION_CONFLICT", "企业创建冲突", 409) from exc
    return JSONResponse(
        status_code=201,
        content=body,
        headers={"Idempotent-Replayed": "false"},
    )


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
    request: Request,
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
    await session.flush()
    _record_organization_change(
        session,
        request,
        actor_id=current_user.id,
        organization_id=organization_id,
        action="organization.invite.create",
        resource_type="organization_invite",
        resource_id=invite.id,
        event_type="OrganizationInviteCreated.v1",
        payload={"inviteId": str(invite.id), "role": str(invite.role)},
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DomainError("INVITE_CONFLICT", "邀请创建冲突", 409) from exc
    await set_tenant_context(session, organization_id, current_user.id)
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
    request: Request,
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
    _record_organization_change(
        session,
        request,
        actor_id=current_user.id,
        organization_id=organization_id,
        action="organization.invite.revoke",
        resource_type="organization_invite",
        resource_id=invite.id,
        event_type="OrganizationInviteRevoked.v1",
        payload={"inviteId": str(invite.id)},
    )
    await session.commit()
    return Response(status_code=204)


@invite_router.post("/{token}/accept", response_model=MemberRead, status_code=201)
async def accept_invite(
    token: str,
    current_user: CurrentUser,
    session: DbSession,
    request: Request,
) -> MemberRead:
    token_hash = hashlib.sha256(token.encode()).digest()
    await resolve_invite_tenant(session, token_hash, current_user.id)
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
    _record_organization_change(
        session,
        request,
        actor_id=current_user.id,
        organization_id=invite.organization_id,
        action="organization.invite.accept",
        resource_type="organization_invite",
        resource_id=invite.id,
        event_type="OrganizationInviteAccepted.v1",
        payload={"inviteId": str(invite.id), "memberId": str(current_user.id)},
    )
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


@router.patch("/{organization_id}/members/{member_id}", response_model=MemberRead)
async def update_member(
    organization_id: UUID,
    member_id: UUID,
    payload: MemberRoleUpdate,
    current_user: CurrentUser,
    session: DbSession,
    request: Request,
) -> MemberRead:
    target = await change_member_role(
        session, organization_id, current_user.id, member_id, payload.role
    )
    user = await session.get(UserModel, member_id)
    _record_organization_change(
        session,
        request,
        actor_id=current_user.id,
        organization_id=organization_id,
        action="organization.member.role.update",
        resource_type="organization_member",
        resource_id=member_id,
        event_type="OrganizationMemberRoleChanged.v1",
        payload={"memberId": str(member_id), "role": str(target.role)},
    )
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
    request: Request,
) -> Response:
    await remove_organization_member(
        session, organization_id, current_user.id, member_id
    )
    trace_id = getattr(request.state, "trace_id", None)
    record_audit(
        session,
        actor_id=current_user.id,
        action="organization.member.remove",
        resource_type="organization_member",
        resource_id=member_id,
        organization_id=organization_id,
        trace_id=trace_id,
        detail={"memberId": str(member_id)},
    )
    record_outbox(
        session,
        organization_id=organization_id,
        aggregate_type="organization",
        aggregate_id=organization_id,
        event_type="OrganizationMemberRemoved.v1",
        aggregate_version=1,
        trace_id=trace_id,
        payload={"memberId": str(member_id)},
    )
    await session.commit()
    return Response(status_code=204)
