from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_api.common.errors import DomainError
from platform_api.db.models import OrganizationMemberModel
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
