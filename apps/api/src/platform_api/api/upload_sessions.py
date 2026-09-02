from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
from platform_api.db.models import (
    OrganizationModel,
    ProjectMemberModel,
    ProjectModel,
    UploadSessionModel,
)
from platform_api.db.session import get_session
from platform_api.modules.artifact.domain import (
    ACTIVE_UPLOAD_STATUSES,
    UploadSessionStatus,
    require_upload_session_cancellable,
)
from platform_api.modules.organization.domain import OrganizationRole
from platform_api.modules.project.domain import ProjectRole, ProjectStatus
from platform_api.settings import get_settings

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/projects/{project_id}/upload-sessions",
    tags=["upload-sessions"],
    responses=PROTECTED_ERROR_RESPONSES,
)
DbSession = Annotated[AsyncSession, Depends(get_session)]
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
OBJECT_KEY_PATTERN = re.compile(r"^v1/o/[0-9a-f]{32}$")


class UploadSessionCreate(StrictModel):
    display_name: str = Field(min_length=1, max_length=512)
    size_bytes: int = Field(gt=0)
    sha256: str = Field(min_length=64, max_length=64)
    content_type: str = Field(min_length=1, max_length=255)

    @field_validator("display_name", "content_type")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or any(ord(character) < 32 or ord(character) == 127 for character in normalized):
            raise ValueError("control characters are not allowed")
        return normalized

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return value


class UploadSessionRead(StrictOrmModel):
    id: UUID
    organization_id: UUID
    project_id: UUID
    created_by: UUID
    display_name: str
    expected_size: int
    expected_sha256: str
    declared_content_type: str
    status: UploadSessionStatus
    expires_at: datetime
    completed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


async def _authorized_project(
    session: AsyncSession,
    organization_id: UUID,
    project_id: UUID,
    actor_id: UUID,
    *,
    write: bool,
) -> ProjectModel:
    organization_member = await require_organization_member(session, organization_id, actor_id)
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
        member = await session.get(ProjectMemberModel, (project_id, actor_id))
        if member is None:
            raise DomainError("PROJECT_NOT_FOUND", "项目不存在或无权访问", 404)
        if write and member.role not in {ProjectRole.ADMIN, ProjectRole.ENGINEER}:
            raise DomainError("PROJECT_WRITE_REQUIRED", "需要项目工程师权限", 403)
    if write and project.status is not ProjectStatus.ACTIVE:
            raise DomainError("PROJECT_ARCHIVED", "归档项目不可创建资产或任务", 409)
    return project


async def _lock_organization(session: AsyncSession, organization_id: UUID) -> None:
    locked = await session.scalar(
        select(OrganizationModel.id)
        .where(OrganizationModel.id == organization_id)
        .with_for_update()
    )
    if locked is None:
        raise DomainError("ORGANIZATION_NOT_FOUND", "企业不存在或无权访问", 404)


async def _active_quota(session: AsyncSession, organization_id: UUID) -> tuple[int, int]:
    result = (
        await session.execute(
            select(
                func.count(UploadSessionModel.id),
                func.coalesce(func.sum(UploadSessionModel.reserved_bytes), 0),
            ).where(
                UploadSessionModel.organization_id == organization_id,
                UploadSessionModel.status.in_(ACTIVE_UPLOAD_STATUSES),
            )
        )
    ).one()
    return int(result[0]), int(result[1])


def _serialize(upload: UploadSessionModel) -> dict[str, object]:
    return UploadSessionRead.model_validate(upload).model_dump(mode="json")


def _expire_if_needed(upload: UploadSessionModel, now: datetime) -> bool:
    expires_at = upload.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if upload.status in ACTIVE_UPLOAD_STATUSES and expires_at <= now:
        upload.status = UploadSessionStatus.EXPIRED
        upload.reserved_bytes = 0
        return True
    return False


async def _visible_upload(
    session: AsyncSession,
    organization_id: UUID,
    project_id: UUID,
    upload_id: UUID,
    actor_id: UUID,
    *,
    write: bool,
) -> tuple[ProjectModel, UploadSessionModel]:
    project = await _authorized_project(
        session, organization_id, project_id, actor_id, write=write
    )
    upload = await session.scalar(
        select(UploadSessionModel).where(
            UploadSessionModel.id == upload_id,
            UploadSessionModel.organization_id == organization_id,
            UploadSessionModel.project_id == project_id,
        )
    )
    if upload is None:
        raise DomainError("UPLOAD_SESSION_NOT_FOUND", "上传会话不存在或无权访问", 404)
    return project, upload


@router.post("", response_model=UploadSessionRead, status_code=status.HTTP_201_CREATED)
async def create_upload_session(
    organization_id: UUID,
    project_id: UUID,
    payload: UploadSessionCreate,
    current_user: CurrentUser,
    session: DbSession,
    request: Request,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    await _authorized_project(
        session, organization_id, project_id, current_user.id, write=True
    )
    settings = get_settings()
    if payload.size_bytes > settings.upload_max_file_bytes:
        raise DomainError("UPLOAD_TOO_LARGE", "文件超过上传大小限制", 413)
    decision = await begin_idempotent_command(
        session,
        actor_id=current_user.id,
        route_key=f"projects.{project_id}.upload-sessions.create",
        idempotency_key=idempotency_key,
        request_payload=payload.model_dump(mode="json"),
    )
    if decision.is_replay:
        return JSONResponse(
            status_code=decision.replay_status,
            content=decision.replay_body,
            headers={"Idempotent-Replayed": "true"},
        )
    await _lock_organization(session, organization_id)
    active_count, reserved_bytes = await _active_quota(session, organization_id)
    if active_count >= settings.upload_max_active_per_organization:
        raise DomainError("UPLOAD_CONCURRENCY_LIMIT", "企业并发上传会话已达上限", 429)
    if reserved_bytes + payload.size_bytes > settings.upload_max_reserved_bytes_per_organization:
        raise DomainError("QUOTA_EXCEEDED", "企业上传预留容量不足", 409)
    object_key = f"v1/o/{secrets.token_hex(16)}"
    assert OBJECT_KEY_PATTERN.fullmatch(object_key)
    upload = UploadSessionModel(
        organization_id=organization_id,
        project_id=project_id,
        created_by=current_user.id,
        display_name=payload.display_name,
        object_key=object_key,
        expected_size=payload.size_bytes,
        expected_sha256=payload.sha256,
        declared_content_type=payload.content_type,
        status=UploadSessionStatus.PENDING_UPLOAD,
        reserved_bytes=payload.size_bytes,
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.upload_session_ttl_seconds),
    )
    session.add(upload)
    await session.flush()
    trace_id = getattr(request.state, "trace_id", None)
    audit_detail = {
        "sizeBytes": payload.size_bytes,
        "contentType": payload.content_type,
        "status": upload.status.value,
    }
    record_audit(
        session,
        actor_id=current_user.id,
        action="upload_session.create",
        resource_type="upload_session",
        resource_id=upload.id,
        organization_id=organization_id,
        project_id=project_id,
        trace_id=trace_id,
        detail=audit_detail,
    )
    record_outbox(
        session,
        organization_id=organization_id,
        aggregate_type="upload_session",
        aggregate_id=upload.id,
        event_type="UploadSessionCreated.v1",
        aggregate_version=upload.version,
        trace_id=trace_id,
        payload=audit_detail,
    )
    body = _serialize(upload)
    complete_idempotent_command(decision, response_status=201, response_body=body)
    await session.commit()
    return JSONResponse(
        status_code=201,
        content=body,
        headers={"Idempotent-Replayed": "false", "ETag": f'"{upload.version}"'},
    )


@router.get("/{upload_id}", response_model=UploadSessionRead)
async def get_upload_session(
    organization_id: UUID,
    project_id: UUID,
    upload_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
):
    _, upload = await _visible_upload(
        session, organization_id, project_id, upload_id, current_user.id, write=False
    )
    if _expire_if_needed(upload, datetime.now(UTC)):
        await session.commit()
        await session.refresh(upload)
    return upload


@router.post("/{upload_id}:cancel", response_model=UploadSessionRead)
async def cancel_upload_session(
    organization_id: UUID,
    project_id: UUID,
    upload_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
    request: Request,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    project, upload = await _visible_upload(
        session, organization_id, project_id, upload_id, current_user.id, write=True
    )
    decision = await begin_idempotent_command(
        session,
        actor_id=current_user.id,
        route_key=f"upload-sessions.{upload_id}.cancel",
        idempotency_key=idempotency_key,
        request_payload={"uploadSessionId": str(upload_id)},
    )
    if decision.is_replay:
        return JSONResponse(
            status_code=decision.replay_status,
            content=decision.replay_body,
            headers={"Idempotent-Replayed": "true"},
        )
    expired = _expire_if_needed(upload, datetime.now(UTC))
    if not expired:
        require_upload_session_cancellable(upload.status)
        upload.status = UploadSessionStatus.ABORTED
        upload.reserved_bytes = 0
    await session.flush()
    await session.refresh(upload)
    trace_id = getattr(request.state, "trace_id", None)
    detail = {"status": upload.status.value}
    record_audit(
        session,
        actor_id=current_user.id,
        action="upload_session.cancel",
        resource_type="upload_session",
        resource_id=upload.id,
        organization_id=project.organization_id,
        project_id=project.id,
        trace_id=trace_id,
        detail=detail,
    )
    record_outbox(
        session,
        organization_id=project.organization_id,
        aggregate_type="upload_session",
        aggregate_id=upload.id,
        event_type="UploadSessionCancelled.v1" if not expired else "UploadSessionExpired.v1",
        aggregate_version=upload.version,
        trace_id=trace_id,
        payload=detail,
    )
    body = _serialize(upload)
    complete_idempotent_command(decision, response_status=200, response_body=body)
    await session.commit()
    return JSONResponse(
        status_code=200,
        content=body,
        headers={"Idempotent-Replayed": "false", "ETag": f'"{upload.version}"'},
    )
