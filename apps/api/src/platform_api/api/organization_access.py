from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_api.common.errors import DomainError
from platform_api.db.models import OrganizationMemberModel, OrganizationModel
from platform_api.modules.organization.domain import OrganizationRole


async def require_organization_member(
    session: AsyncSession, organization_id: UUID, user_id: UUID
) -> OrganizationMemberModel:
    membership = await session.scalar(
        select(OrganizationMemberModel).where(
            OrganizationMemberModel.organization_id == organization_id,
            OrganizationMemberModel.user_id == user_id,
        )
    )
    if membership is None:
        raise DomainError("ORGANIZATION_NOT_FOUND", "企业不存在或无权访问", 404)
    return membership


async def require_organization_admin(
    session: AsyncSession, organization_id: UUID, user_id: UUID
) -> OrganizationMemberModel:
    membership = await require_organization_member(session, organization_id, user_id)
    if membership.role not in {OrganizationRole.OWNER, OrganizationRole.ADMIN}:
        raise DomainError("ORGANIZATION_ADMIN_REQUIRED", "需要企业管理员权限", 403)
    return membership


async def _lock_and_authorize(
    session: AsyncSession, organization_id: UUID, actor_id: UUID
) -> OrganizationMemberModel:
    organization = await session.scalar(
        select(OrganizationModel)
        .where(OrganizationModel.id == organization_id)
        .with_for_update()
    )
    if organization is None:
        raise DomainError("ORGANIZATION_NOT_FOUND", "企业不存在或无权访问", 404)
    return await require_organization_admin(session, organization_id, actor_id)


async def _target(
    session: AsyncSession, organization_id: UUID, member_id: UUID
) -> OrganizationMemberModel:
    member = await session.scalar(
        select(OrganizationMemberModel).where(
            OrganizationMemberModel.organization_id == organization_id,
            OrganizationMemberModel.user_id == member_id,
        )
    )
    if member is None:
        raise DomainError("MEMBER_NOT_FOUND", "企业成员不存在", 404)
    return member


async def _ensure_other_owner(session: AsyncSession, organization_id: UUID) -> None:
    count = await session.scalar(
        select(func.count())
        .select_from(OrganizationMemberModel)
        .where(
            OrganizationMemberModel.organization_id == organization_id,
            OrganizationMemberModel.role == OrganizationRole.OWNER,
        )
    )
    if count <= 1:
        raise DomainError("LAST_OWNER_REQUIRED", "企业必须至少保留一名所有者", 409)


async def change_member_role(
    session: AsyncSession,
    organization_id: UUID,
    actor_id: UUID,
    member_id: UUID,
    role: OrganizationRole,
) -> OrganizationMemberModel:
    actor = await _lock_and_authorize(session, organization_id, actor_id)
    target = await _target(session, organization_id, member_id)
    if (
        target.role is OrganizationRole.OWNER or role is OrganizationRole.OWNER
    ) and actor.role is not OrganizationRole.OWNER:
        raise DomainError("OWNER_PERMISSION_REQUIRED", "需要企业所有者权限", 403)
    if target.role is OrganizationRole.OWNER and role is not OrganizationRole.OWNER:
        await _ensure_other_owner(session, organization_id)
    target.role = role
    return target


async def remove_organization_member(
    session: AsyncSession, organization_id: UUID, actor_id: UUID, member_id: UUID
) -> OrganizationMemberModel:
    actor = await _lock_and_authorize(session, organization_id, actor_id)
    target = await _target(session, organization_id, member_id)
    if target.role is OrganizationRole.OWNER:
        if actor.role is not OrganizationRole.OWNER:
            raise DomainError("OWNER_PERMISSION_REQUIRED", "需要企业所有者权限", 403)
        await _ensure_other_owner(session, organization_id)
    await session.delete(target)
    return target
