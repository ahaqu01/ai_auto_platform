from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_api.auth.dependencies import CurrentUser
from platform_api.common.errors import DomainError
from platform_api.db.models import OrganizationMemberModel, ProjectModel
from platform_api.db.session import get_session
from platform_api.modules.project.domain import ProjectStatus

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/projects", tags=["projects"]
)
DbSession = Annotated[AsyncSession, Depends(get_session)]


class ProjectCreate(BaseModel):
    code: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=2, max_length=120)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().lower()


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    code: str
    name: str
    status: ProjectStatus


async def require_member(
    session: AsyncSession, organization_id: UUID, user_id: UUID
) -> None:
    membership = await session.scalar(
        select(OrganizationMemberModel).where(
            OrganizationMemberModel.organization_id == organization_id,
            OrganizationMemberModel.user_id == user_id,
        )
    )
    if membership is None:
        raise DomainError("ORGANIZATION_NOT_FOUND", "企业不存在或无权访问", 404)


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    organization_id: UUID,
    payload: ProjectCreate,
    current_user: CurrentUser,
    session: DbSession,
) -> ProjectModel:
    await require_member(session, organization_id, current_user.id)
    project = ProjectModel(
        organization_id=organization_id, code=payload.code, name=payload.name.strip()
    )
    session.add(project)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DomainError("PROJECT_CODE_EXISTS", "项目编码已存在", 409) from exc
    await session.refresh(project)
    return project


@router.get("", response_model=list[ProjectRead])
async def list_projects(
    organization_id: UUID, current_user: CurrentUser, session: DbSession
) -> list[ProjectModel]:
    await require_member(session, organization_id, current_user.id)
    result = await session.scalars(
        select(ProjectModel)
        .where(ProjectModel.organization_id == organization_id)
        .order_by(ProjectModel.created_at)
    )
    return list(result)
