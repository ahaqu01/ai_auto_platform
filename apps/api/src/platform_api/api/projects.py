import base64
import json
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import Field, field_validator, model_validator
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from platform_api.api.organization_access import require_organization_member
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
from platform_api.common.tenancy import set_tenant_context
from platform_api.db.models import (
    OrganizationMemberModel,
    ProjectMemberModel,
    ProjectModel,
)
from platform_api.db.session import get_session
from platform_api.modules.organization.domain import OrganizationRole
from platform_api.modules.project.domain import ProjectRole, ProjectStatus

PROJECT_RESPONSES = {
    **PROTECTED_ERROR_RESPONSES,
    412: {"description": "If-Match does not match the current resource version"},
    428: {"description": "If-Match is required"},
}
router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/projects",
    tags=["projects"],
    responses=PROJECT_RESPONSES,
)
DbSession = Annotated[AsyncSession, Depends(get_session)]


class ProjectCreate(StrictModel):
    code: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=4000)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().lower()


class ProjectUpdate(StrictModel):
    code: str | None = Field(
        default=None, min_length=2, max_length=50, pattern=r"^[a-z0-9][a-z0-9-]*$"
    )
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=4000)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        return value.strip().lower() if value is not None else None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("at least one project field is required")
        return self


class ProjectRead(StrictOrmModel):
    id: UUID
    organization_id: UUID
    code: str
    name: str
    description: str | None
    status: ProjectStatus
    version: int
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProjectMemberCreate(StrictModel):
    member_id: UUID
    role: ProjectRole


class ProjectMemberUpdate(StrictModel):
    role: ProjectRole


class ProjectMemberRead(StrictOrmModel):
    project_id: UUID
    user_id: UUID
    organization_id: UUID
    role: ProjectRole


def _record_project_member_change(
    session: AsyncSession,
    request: Request,
    *,
    actor_id: UUID,
    project: ProjectModel,
    member_id: UUID,
    action: str,
    event_type: str,
    role: ProjectRole | None = None,
) -> None:
    trace_id = getattr(request.state, "trace_id", None)
    payload = {"memberId": str(member_id)}
    if role is not None:
        payload["role"] = str(role)
    record_audit(
        session,
        actor_id=actor_id,
        action=action,
        resource_type="project_member",
        resource_id=member_id,
        organization_id=project.organization_id,
        project_id=project.id,
        trace_id=trace_id,
        detail=payload,
    )
    record_outbox(
        session,
        organization_id=project.organization_id,
        aggregate_type="project",
        aggregate_id=project.id,
        event_type=event_type,
        aggregate_version=project.version,
        trace_id=trace_id,
        payload=payload,
    )


def _etag(version: int) -> str:
    return f'"{version}"'


def _expected_version(if_match: str | None) -> int:
    if if_match is None:
        raise DomainError("IF_MATCH_REQUIRED", "更新项目必须提供 If-Match", 428)
    value = if_match.strip()
    value = value.removeprefix("W/")
    if len(value) < 3 or value[0] != '"' or value[-1] != '"':
        raise DomainError("INVALID_IF_MATCH", "If-Match 必须是带引号的整数版本", 400)
    try:
        return int(value[1:-1])
    except ValueError as exc:
        raise DomainError(
            "INVALID_IF_MATCH", "If-Match 必须是带引号的整数版本", 400
        ) from exc


def _encode_cursor(project: ProjectModel) -> str:
    raw = json.dumps(
        [project.created_at.isoformat(), str(project.id)], separators=(",", ":")
    ).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        created_at, project_id = json.loads(raw)
        return datetime.fromisoformat(created_at), UUID(project_id)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise DomainError("INVALID_CURSOR", "分页游标无效", 400) from exc


async def _visible_project(
    session: AsyncSession, organization_id: UUID, project_id: UUID, actor_id: UUID
) -> tuple[ProjectModel, OrganizationMemberModel]:
    organization_member = await require_organization_member(
        session, organization_id, actor_id
    )
    project = await session.scalar(
        select(ProjectModel).where(
            ProjectModel.id == project_id,
            ProjectModel.organization_id == organization_id,
            ProjectModel.deleted_at.is_(None),
        )
    )
    if project is None:
        raise DomainError("PROJECT_NOT_FOUND", "项目不存在或无权访问", 404)
    if organization_member.role not in {OrganizationRole.OWNER, OrganizationRole.ADMIN}:
        project_member = await session.get(ProjectMemberModel, (project_id, actor_id))
        if project_member is None:
            raise DomainError("PROJECT_NOT_FOUND", "项目不存在或无权访问", 404)
    return project, organization_member


async def _require_project_admin(
    session: AsyncSession, organization_id: UUID, project_id: UUID, actor_id: UUID
) -> ProjectModel:
    project, organization_member = await _visible_project(
        session, organization_id, project_id, actor_id
    )
    if organization_member.role in {OrganizationRole.OWNER, OrganizationRole.ADMIN}:
        return project
    project_member = await session.get(ProjectMemberModel, (project_id, actor_id))
    if project_member is None or project_member.role is not ProjectRole.ADMIN:
        raise DomainError("PROJECT_ADMIN_REQUIRED", "需要项目管理员权限", 403)
    return project


def _check_version(project: ProjectModel, if_match: str | None) -> None:
    if project.version != _expected_version(if_match):
        raise DomainError("VERSION_MISMATCH", "项目版本已变化，请刷新后重试", 412)


async def _commit_project(
    session: AsyncSession, project: ProjectModel, actor_id: UUID
) -> ProjectModel:
    organization_id = project.organization_id
    try:
        await session.commit()
    except StaleDataError as exc:
        await session.rollback()
        raise DomainError(
            "VERSION_MISMATCH", "项目版本已变化，请刷新后重试", 412
        ) from exc
    except IntegrityError as exc:
        await session.rollback()
        raise DomainError("PROJECT_CODE_EXISTS", "项目编码已存在", 409) from exc
    await set_tenant_context(session, organization_id, actor_id)
    await session.refresh(project)
    return project


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    organization_id: UUID,
    payload: ProjectCreate,
    current_user: CurrentUser,
    session: DbSession,
    response: Response,
    request: Request,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ProjectModel | JSONResponse:
    membership = await require_organization_member(
        session, organization_id, current_user.id
    )
    if membership.role not in {OrganizationRole.OWNER, OrganizationRole.ADMIN}:
        raise DomainError("ORGANIZATION_ADMIN_REQUIRED", "需要企业管理员权限", 403)
    decision = await begin_idempotent_command(
        session,
        actor_id=current_user.id,
        route_key=f"organizations.{organization_id}.projects.create",
        idempotency_key=idempotency_key,
        request_payload=payload.model_dump(mode="json"),
    )
    if decision.is_replay:
        return JSONResponse(
            status_code=decision.replay_status,
            content=decision.replay_body,
            headers={"Idempotent-Replayed": "true"},
        )
    project = ProjectModel(
        organization_id=organization_id,
        code=payload.code,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
    )
    session.add(project)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise DomainError("PROJECT_CODE_EXISTS", "项目编码已存在", 409) from exc
    session.add(
        ProjectMemberModel(
            organization_id=organization_id,
            project_id=project.id,
            user_id=current_user.id,
            role=ProjectRole.ADMIN,
        )
    )
    trace_id = getattr(request.state, "trace_id", None)
    record_audit(
        session,
        actor_id=current_user.id,
        action="project.create",
        resource_type="project",
        resource_id=project.id,
        organization_id=organization_id,
        project_id=project.id,
        trace_id=trace_id,
        detail={"code": project.code},
    )
    record_outbox(
        session,
        organization_id=organization_id,
        aggregate_type="project",
        aggregate_id=project.id,
        event_type="ProjectCreated.v1",
        aggregate_version=project.version,
        trace_id=trace_id,
        payload={"code": project.code},
    )
    body = ProjectRead.model_validate(project).model_dump(mode="json")
    complete_idempotent_command(decision, response_status=201, response_body=body)
    await _commit_project(session, project, current_user.id)
    response.headers["ETag"] = _etag(project.version)
    return JSONResponse(
        status_code=201,
        content=body,
        headers={"ETag": _etag(project.version), "Idempotent-Replayed": "false"},
    )


@router.get("", response_model=list[ProjectRead])
async def list_projects(
    organization_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> list[ProjectModel]:
    membership = await require_organization_member(
        session, organization_id, current_user.id
    )
    statement = select(ProjectModel).where(
        ProjectModel.organization_id == organization_id,
        ProjectModel.deleted_at.is_(None),
    )
    if membership.role not in {OrganizationRole.OWNER, OrganizationRole.ADMIN}:
        statement = statement.join(ProjectMemberModel).where(
            ProjectMemberModel.user_id == current_user.id
        )
    if cursor:
        created_at, project_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                ProjectModel.created_at > created_at,
                and_(
                    ProjectModel.created_at == created_at, ProjectModel.id > project_id
                ),
            )
        )
    projects = list(
        await session.scalars(
            statement.order_by(ProjectModel.created_at, ProjectModel.id).limit(
                limit + 1
            )
        )
    )
    if len(projects) > limit:
        response.headers["X-Next-Cursor"] = _encode_cursor(projects[limit - 1])
        projects = projects[:limit]
    return projects


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    organization_id: UUID,
    project_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
    response: Response,
) -> ProjectModel:
    project, _ = await _visible_project(
        session, organization_id, project_id, current_user.id
    )
    response.headers["ETag"] = _etag(project.version)
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    organization_id: UUID,
    project_id: UUID,
    payload: ProjectUpdate,
    current_user: CurrentUser,
    session: DbSession,
    response: Response,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ProjectModel:
    project = await _require_project_admin(
        session, organization_id, project_id, current_user.id
    )
    _check_version(project, if_match)
    if "code" in payload.model_fields_set:
        project.code = payload.code  # type: ignore[assignment]
    if "name" in payload.model_fields_set:
        project.name = payload.name.strip()  # type: ignore[union-attr]
    if "description" in payload.model_fields_set:
        project.description = (
            payload.description.strip() if payload.description else None
        )
    await _commit_project(session, project, current_user.id)
    response.headers["ETag"] = _etag(project.version)
    return project


async def _change_status(
    session: AsyncSession,
    project: ProjectModel,
    target: ProjectStatus,
    if_match: str | None,
    actor_id: UUID,
    trace_id: str | None,
) -> ProjectModel:
    _check_version(project, if_match)
    project.status = target
    project.archived_at = (
        datetime.now(UTC) if target is ProjectStatus.ARCHIVED else None
    )
    action = (
        "project.archive" if target is ProjectStatus.ARCHIVED else "project.restore"
    )
    event_type = (
        "ProjectArchived.v1"
        if target is ProjectStatus.ARCHIVED
        else "ProjectRestored.v1"
    )
    record_audit(
        session,
        actor_id=actor_id,
        action=action,
        resource_type="project",
        resource_id=project.id,
        organization_id=project.organization_id,
        project_id=project.id,
        trace_id=trace_id,
        detail={"targetStatus": target.value},
    )
    record_outbox(
        session,
        organization_id=project.organization_id,
        aggregate_type="project",
        aggregate_id=project.id,
        event_type=event_type,
        aggregate_version=project.version + 1,
        trace_id=trace_id,
        payload={"status": target.value},
    )
    return await _commit_project(session, project, actor_id)


@router.post("/{project_id}:archive", response_model=ProjectRead)
async def archive_project(
    organization_id: UUID,
    project_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
    response: Response,
    request: Request,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ProjectModel:
    project = await _require_project_admin(
        session, organization_id, project_id, current_user.id
    )
    project = await _change_status(
        session,
        project,
        ProjectStatus.ARCHIVED,
        if_match,
        current_user.id,
        getattr(request.state, "trace_id", None),
    )
    response.headers["ETag"] = _etag(project.version)
    return project


@router.post("/{project_id}:restore", response_model=ProjectRead)
async def restore_project(
    organization_id: UUID,
    project_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
    response: Response,
    request: Request,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ProjectModel:
    project = await _require_project_admin(
        session, organization_id, project_id, current_user.id
    )
    project = await _change_status(
        session,
        project,
        ProjectStatus.ACTIVE,
        if_match,
        current_user.id,
        getattr(request.state, "trace_id", None),
    )
    response.headers["ETag"] = _etag(project.version)
    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    organization_id: UUID,
    project_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> Response:
    project = await _require_project_admin(
        session, organization_id, project_id, current_user.id
    )
    _check_version(project, if_match)
    project.deleted_at = datetime.now(UTC)
    await _commit_project(session, project, current_user.id)
    return Response(status_code=204)


@router.get("/{project_id}/members", response_model=list[ProjectMemberRead])
async def list_project_members(
    organization_id: UUID,
    project_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
) -> list[ProjectMemberModel]:
    await _visible_project(session, organization_id, project_id, current_user.id)
    return list(
        await session.scalars(
            select(ProjectMemberModel)
            .where(ProjectMemberModel.project_id == project_id)
            .order_by(ProjectMemberModel.created_at)
        )
    )


@router.post("/{project_id}/members", response_model=ProjectMemberRead, status_code=201)
async def add_project_member(
    organization_id: UUID,
    project_id: UUID,
    payload: ProjectMemberCreate,
    current_user: CurrentUser,
    session: DbSession,
    request: Request,
) -> ProjectMemberModel:
    project = await _require_project_admin(
        session, organization_id, project_id, current_user.id
    )
    organization_member = await session.get(
        OrganizationMemberModel, (organization_id, payload.member_id)
    )
    if organization_member is None:
        raise DomainError("ORGANIZATION_MEMBER_REQUIRED", "只能添加当前企业成员", 409)
    member = ProjectMemberModel(
        organization_id=organization_id,
        project_id=project_id,
        user_id=payload.member_id,
        role=payload.role,
    )
    session.add(member)
    _record_project_member_change(
        session,
        request,
        actor_id=current_user.id,
        project=project,
        member_id=payload.member_id,
        action="project.member.add",
        event_type="ProjectMemberAdded.v1",
        role=payload.role,
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DomainError("PROJECT_MEMBER_EXISTS", "项目成员已存在", 409) from exc
    await set_tenant_context(session, organization_id, current_user.id)
    await session.refresh(member)
    return member


@router.patch("/{project_id}/members/{member_id}", response_model=ProjectMemberRead)
async def update_project_member(
    organization_id: UUID,
    project_id: UUID,
    member_id: UUID,
    payload: ProjectMemberUpdate,
    current_user: CurrentUser,
    session: DbSession,
    request: Request,
) -> ProjectMemberModel:
    project = await _require_project_admin(
        session, organization_id, project_id, current_user.id
    )
    member = await session.get(ProjectMemberModel, (project_id, member_id))
    if member is None:
        raise DomainError("PROJECT_MEMBER_NOT_FOUND", "项目成员不存在", 404)
    member.role = payload.role
    _record_project_member_change(
        session,
        request,
        actor_id=current_user.id,
        project=project,
        member_id=member_id,
        action="project.member.role.update",
        event_type="ProjectMemberRoleChanged.v1",
        role=payload.role,
    )
    await session.commit()
    await set_tenant_context(session, organization_id, current_user.id)
    await session.refresh(member)
    return member


@router.delete("/{project_id}/members/{member_id}", status_code=204)
async def remove_project_member(
    organization_id: UUID,
    project_id: UUID,
    member_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
    request: Request,
) -> Response:
    project = await _require_project_admin(
        session, organization_id, project_id, current_user.id
    )
    member = await session.get(ProjectMemberModel, (project_id, member_id))
    if member is None:
        raise DomainError("PROJECT_MEMBER_NOT_FOUND", "项目成员不存在", 404)
    _record_project_member_change(
        session,
        request,
        actor_id=current_user.id,
        project=project,
        member_id=member_id,
        action="project.member.remove",
        event_type="ProjectMemberRemoved.v1",
    )
    await session.delete(member)
    await session.commit()
    return Response(status_code=204)
