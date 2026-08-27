from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from platform_api.common.errors import DomainError

RUNTIME_ROLE = "platform_runtime"


def _is_postgresql(session: AsyncSession) -> bool:
    return session.get_bind().dialect.name == "postgresql"


async def activate_actor_context(session: AsyncSession, actor_id: UUID) -> None:
    if not _is_postgresql(session):
        return
    await session.execute(text(f"SET LOCAL ROLE {RUNTIME_ROLE}"))
    await session.execute(select(func.set_config("app.actor_id", str(actor_id), True)))
    await session.execute(select(func.set_config("app.organization_id", "", True)))


async def set_tenant_context(
    session: AsyncSession, organization_id: UUID, actor_id: UUID
) -> None:
    if not _is_postgresql(session):
        return
    await session.execute(text(f"SET LOCAL ROLE {RUNTIME_ROLE}"))
    await session.execute(select(func.set_config("app.actor_id", str(actor_id), True)))
    await session.execute(
        select(func.set_config("app.organization_id", str(organization_id), True))
    )


async def resolve_invite_tenant(
    session: AsyncSession, token_hash: bytes, actor_id: UUID
) -> UUID:
    if not _is_postgresql(session):
        from platform_api.db.models import OrganizationInviteModel

        organization_id = await session.scalar(
            select(OrganizationInviteModel.organization_id).where(
                OrganizationInviteModel.token_hash == token_hash
            )
        )
    else:
        organization_id = await session.scalar(
            select(func.resolve_invite_organization(token_hash))
        )
    if organization_id is None:
        raise DomainError("INVITE_NOT_FOUND", "邀请不存在", 404)
    await set_tenant_context(session, organization_id, actor_id)
    return organization_id
