from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_api.common.errors import DomainError
from platform_api.db.models import OrganizationMemberModel, OrganizationModel, UserModel
from platform_api.db.session import get_session
from platform_api.modules.organization.domain import OrganizationRole

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    owner_email: str = Field(min_length=3, max_length=320)
    owner_display_name: str = Field(min_length=1, max_length=120)


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate, session: AsyncSession = Depends(get_session)
) -> OrganizationModel:
    email = payload.owner_email.strip().lower()
    user = await session.scalar(select(UserModel).where(UserModel.email == email))
    if user is None:
        user = UserModel(email=email, display_name=payload.owner_display_name.strip())
        session.add(user)
        await session.flush()
    organization = OrganizationModel(name=payload.name.strip())
    session.add(organization)
    await session.flush()
    session.add(
        OrganizationMemberModel(
            organization_id=organization.id,
            user_id=user.id,
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
    user_id: UUID, session: AsyncSession = Depends(get_session)
) -> list[OrganizationModel]:
    result = await session.scalars(
        select(OrganizationModel)
        .join(OrganizationMemberModel)
        .where(OrganizationMemberModel.user_id == user_id)
        .order_by(OrganizationModel.created_at)
    )
    return list(result)
