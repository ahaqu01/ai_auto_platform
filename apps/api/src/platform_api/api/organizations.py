from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_api.auth.dependencies import CurrentUser
from platform_api.common.api_contract import (
    PROTECTED_ERROR_RESPONSES,
    StrictModel,
    StrictOrmModel,
)
from platform_api.common.errors import DomainError
from platform_api.db.models import OrganizationMemberModel, OrganizationModel
from platform_api.db.session import get_session
from platform_api.modules.organization.domain import OrganizationRole

router = APIRouter(
    prefix="/api/v1/organizations",
    tags=["organizations"],
    responses=PROTECTED_ERROR_RESPONSES,
)
DbSession = Annotated[AsyncSession, Depends(get_session)]


class OrganizationCreate(StrictModel):
    name: str = Field(min_length=2, max_length=120)


class OrganizationRead(StrictOrmModel):
    id: UUID
    name: str


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
