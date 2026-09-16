from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, cast
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
from platform_api.common.tenancy import set_tenant_context
from platform_api.db.models import (
    ArtifactModel,
    OrganizationModel,
    ProjectMemberModel,
    ProjectModel,
    UploadPartModel,
    UploadSessionModel,
)
from platform_api.db.session import get_session
from platform_api.modules.artifact.completion import (
    VerificationStoragePort,
    verify_object,
)
from platform_api.modules.artifact.domain import (
    ACTIVE_UPLOAD_STATUSES,
    ArtifactStatus,
    IntegrityStatus,
    SecurityScanStatus,
    UploadSessionStatus,
    require_upload_session_cancellable,
)
from platform_api.modules.artifact.storage import (
    CompletedPart,
    ObjectStorageError,
    ObjectStoragePort,
    StorageErrorCode,
)
from platform_api.modules.artifact.storage_runtime import build_object_storage
from platform_api.modules.organization.domain import OrganizationRole
from platform_api.modules.project.domain import ProjectRole, ProjectStatus
from platform_api.settings import Settings, get_settings

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/projects/{project_id}/upload-sessions",
    tags=["upload-sessions"],
    responses=PROTECTED_ERROR_RESPONSES,
)
DbSession = Annotated[AsyncSession, Depends(get_session)]


def get_object_storage(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ObjectStoragePort | None:
    """Fail-closed deployment composition for the pinned storage gateway."""
    return build_object_storage(settings)


Storage = Annotated[ObjectStoragePort | None, Depends(get_object_storage)]
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
        if not normalized or any(
            ord(character) < 32 or ord(character) == 127 for character in normalized
        ):
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


class UploadPartSignRequest(StrictModel):
    part_numbers: list[int] = Field(min_length=1, max_length=100)
    expires_in_seconds: int = Field(default=900, ge=60, le=3600)

    @field_validator("part_numbers")
    @classmethod
    def validate_part_numbers(cls, value: list[int]) -> list[int]:
        if any(number < 1 or number > 10_000 for number in value):
            raise ValueError("part number must be between 1 and 10000")
        if len(set(value)) != len(value):
            raise ValueError("part numbers must be unique")
        return value


class UploadPartSigned(StrictModel):
    part_number: int
    url: str
    expires_in_seconds: int


class UploadPartRegister(StrictModel):
    etag: str = Field(min_length=1, max_length=512)
    size_bytes: int = Field(gt=0)

    @field_validator("etag")
    @classmethod
    def validate_etag(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or any(
            ord(character) < 32 or ord(character) == 127 for character in normalized
        ):
            raise ValueError("invalid etag")
        return normalized


class UploadCompletePart(StrictModel):
    part_number: int = Field(ge=1, le=10_000)
    etag: str = Field(min_length=1, max_length=512)


class UploadCompleteRequest(StrictModel):
    parts: list[UploadCompletePart] = Field(min_length=1, max_length=10_000)

    @field_validator("parts")
    @classmethod
    def validate_parts(
        cls, value: list[UploadCompletePart]
    ) -> list[UploadCompletePart]:
        numbers = [part.part_number for part in value]
        if numbers != sorted(numbers) or len(numbers) != len(set(numbers)):
            raise ValueError("parts must be unique and sorted by part number")
        return value


class ArtifactRead(StrictOrmModel):
    id: UUID
    upload_session_id: UUID
    organization_id: UUID
    project_id: UUID
    created_by: UUID
    display_name: str
    size_bytes: int
    expected_sha256: str
    verified_sha256: str
    declared_content_type: str
    detected_content_type: str | None
    integrity_status: IntegrityStatus
    security_scan_status: SecurityScanStatus
    status: ArtifactStatus
    version: int
    created_at: datetime
    updated_at: datetime


class UploadPartRead(StrictOrmModel):
    part_number: int
    etag: str
    size_bytes: int
    created_at: datetime
    updated_at: datetime


def _storage_required(storage: ObjectStoragePort | None) -> ObjectStoragePort:
    if storage is None:
        raise DomainError("STORAGE_UNAVAILABLE", "对象存储运行时尚未配置", 503)
    return storage


def _storage_failure(exc: ObjectStorageError) -> DomainError:
    return DomainError("STORAGE_UNAVAILABLE", "对象存储暂时不可用", 503)


async def _authorized_project(
    session: AsyncSession,
    organization_id: UUID,
    project_id: UUID,
    actor_id: UUID,
    *,
    write: bool,
) -> ProjectModel:
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


async def _active_quota(
    session: AsyncSession, organization_id: UUID
) -> tuple[int, int]:
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
    if (
        reserved_bytes + payload.size_bytes
        > settings.upload_max_reserved_bytes_per_organization
    ):
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
        expires_at=datetime.now(UTC)
        + timedelta(seconds=settings.upload_session_ttl_seconds),
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
    request: Request,
    current_user: CurrentUser,
    session: DbSession,
):
    _, upload = await _visible_upload(
        session, organization_id, project_id, upload_id, current_user.id, write=False
    )
    if _expire_if_needed(upload, datetime.now(UTC)):
        await session.flush()
        await session.refresh(upload)
        trace_id = getattr(request.state, "trace_id", None)
        detail = {"status": upload.status.value}
        record_audit(
            session,
            actor_id=current_user.id,
            action="upload_session.expire",
            resource_type="upload_session",
            resource_id=upload.id,
            organization_id=organization_id,
            project_id=project_id,
            trace_id=trace_id,
            detail=detail,
        )
        record_outbox(
            session,
            organization_id=organization_id,
            aggregate_type="upload_session",
            aggregate_id=upload.id,
            event_type="UploadSessionExpired.v1",
            aggregate_version=upload.version,
            trace_id=trace_id,
            payload=detail,
        )
        await session.commit()
        await session.refresh(upload)
    return upload


@router.post("/{upload_id}/parts:sign", response_model=list[UploadPartSigned])
async def sign_upload_parts(
    organization_id: UUID,
    project_id: UUID,
    upload_id: UUID,
    payload: UploadPartSignRequest,
    current_user: CurrentUser,
    session: DbSession,
    storage: Storage,
    request: Request,
):
    await _authorized_project(
        session, organization_id, project_id, current_user.id, write=True
    )
    upload = await session.scalar(
        select(UploadSessionModel)
        .where(
            UploadSessionModel.id == upload_id,
            UploadSessionModel.organization_id == organization_id,
            UploadSessionModel.project_id == project_id,
        )
        .with_for_update()
    )
    if upload is None:
        raise DomainError("UPLOAD_SESSION_NOT_FOUND", "上传会话不存在或无权限访问", 404)
    if _expire_if_needed(upload, datetime.now(UTC)):
        await session.commit()
        raise DomainError("UPLOAD_EXPIRED", "上传会话已过期", 409)
    port = _storage_required(storage)
    initialized = upload.status is UploadSessionStatus.PENDING_UPLOAD
    try:
        if initialized:
            upload.storage_upload_id = await port.start_multipart(
                upload.object_key, upload.declared_content_type
            )
            upload.status = UploadSessionStatus.UPLOADING
            await session.flush()
            trace_id = getattr(request.state, "trace_id", None)
            detail = {"status": upload.status.value}
            record_audit(
                session,
                actor_id=current_user.id,
                action="upload_session.multipart.initialize",
                resource_type="upload_session",
                resource_id=upload.id,
                organization_id=organization_id,
                project_id=project_id,
                trace_id=trace_id,
                detail=detail,
            )
            record_outbox(
                session,
                organization_id=organization_id,
                aggregate_type="upload_session",
                aggregate_id=upload.id,
                event_type="UploadSessionMultipartInitialized.v1",
                aggregate_version=upload.version,
                trace_id=trace_id,
                payload=detail,
            )
            # Persist the remote upload id before signing.  A signing timeout must
            # remain resumable and visible to expiry cleanup instead of creating
            # an unreachable multipart upload in object storage.
            await session.commit()
        elif upload.status is not UploadSessionStatus.UPLOADING:
            raise DomainError(
                "UPLOAD_STATE_CONFLICT", "上传会话状态不允许分片签名", 409
            )
        if not upload.storage_upload_id:
            raise DomainError(
                "UPLOAD_STATE_CONFLICT", "上传会话缺少远端 Multipart 标识", 409
            )
        signed = []
        for part_number in payload.part_numbers:
            presigned = await port.sign_upload_part(
                upload.object_key,
                upload.storage_upload_id,
                part_number,
                payload.expires_in_seconds,
            )
            signed.append(
                UploadPartSigned(
                    part_number=part_number,
                    url=presigned.url,
                    expires_in_seconds=presigned.expires_in_seconds,
                )
            )
    except ObjectStorageError as exc:
        raise _storage_failure(exc) from exc
    await session.commit()
    return signed


@router.put("/{upload_id}/parts/{part_number}", response_model=UploadPartRead)
async def register_upload_part(
    organization_id: UUID,
    project_id: UUID,
    upload_id: UUID,
    part_number: int,
    payload: UploadPartRegister,
    current_user: CurrentUser,
    session: DbSession,
    request: Request,
):
    if part_number < 1 or part_number > 10_000:
        raise DomainError("INVALID_PART_NUMBER", "分片编号必须在 1 到 10000 之间", 422)
    _, upload = await _visible_upload(
        session, organization_id, project_id, upload_id, current_user.id, write=True
    )
    if _expire_if_needed(upload, datetime.now(UTC)):
        await session.commit()
        raise DomainError("UPLOAD_EXPIRED", "上传会话已过期", 409)
    if upload.status is not UploadSessionStatus.UPLOADING:
        raise DomainError("UPLOAD_STATE_CONFLICT", "上传会话状态不允许登记分片", 409)
    part = await session.get(UploadPartModel, (upload.id, part_number))
    if part is not None:
        if part.etag != payload.etag or part.size_bytes != payload.size_bytes:
            raise DomainError("UPLOAD_PART_CONFLICT", "分片已使用不同内容登记", 409)
        return part
    part = UploadPartModel(
        upload_session_id=upload.id,
        organization_id=organization_id,
        part_number=part_number,
        etag=payload.etag,
        size_bytes=payload.size_bytes,
    )
    session.add(part)
    await session.flush()
    trace_id = getattr(request.state, "trace_id", None)
    detail = {"partNumber": part_number, "sizeBytes": payload.size_bytes}
    record_audit(
        session,
        actor_id=current_user.id,
        action="upload_part.register",
        resource_type="upload_session",
        resource_id=upload.id,
        organization_id=organization_id,
        project_id=project_id,
        trace_id=trace_id,
        detail=detail,
    )
    record_outbox(
        session,
        organization_id=organization_id,
        aggregate_type="upload_session",
        aggregate_id=upload.id,
        event_type="UploadPartRegistered.v1",
        aggregate_version=upload.version,
        trace_id=trace_id,
        payload=detail,
    )
    await session.commit()
    await set_tenant_context(session, organization_id, current_user.id)
    await session.refresh(part)
    return part


@router.get("/{upload_id}/parts", response_model=list[UploadPartRead])
async def list_upload_parts(
    organization_id: UUID,
    project_id: UUID,
    upload_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
):
    _, upload = await _visible_upload(
        session, organization_id, project_id, upload_id, current_user.id, write=False
    )
    return list(
        await session.scalars(
            select(UploadPartModel)
            .where(UploadPartModel.upload_session_id == upload.id)
            .order_by(UploadPartModel.part_number)
        )
    )


@router.post(
    "/{upload_id}:complete",
    response_model=ArtifactRead,
    status_code=status.HTTP_201_CREATED,
)
async def complete_upload_session(
    organization_id: UUID,
    project_id: UUID,
    upload_id: UUID,
    payload: UploadCompleteRequest,
    current_user: CurrentUser,
    session: DbSession,
    storage: Storage,
    request: Request,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    if idempotency_key is None:
        raise DomainError("IDEMPOTENCY_KEY_REQUIRED", "必须提供 Idempotency-Key", 428)
    if not 16 <= len(idempotency_key) <= 128:
        raise DomainError(
            "INVALID_IDEMPOTENCY_KEY", "Idempotency-Key 长度必须为 16 到 128", 400
        )
    await _authorized_project(
        session, organization_id, project_id, current_user.id, write=True
    )
    upload = await session.scalar(
        select(UploadSessionModel)
        .where(
            UploadSessionModel.id == upload_id,
            UploadSessionModel.organization_id == organization_id,
            UploadSessionModel.project_id == project_id,
        )
        .with_for_update()
    )
    if upload is None:
        raise DomainError("UPLOAD_SESSION_NOT_FOUND", "上传会话不存在或无权访问", 404)
    existing = await session.scalar(
        select(ArtifactModel).where(ArtifactModel.upload_session_id == upload.id)
    )
    if upload.status is UploadSessionStatus.COMPLETED and existing is not None:
        return JSONResponse(
            status_code=200,
            content=ArtifactRead.model_validate(existing).model_dump(mode="json"),
            headers={"Idempotent-Replayed": "true"},
        )
    if _expire_if_needed(upload, datetime.now(UTC)):
        await session.commit()
        raise DomainError("UPLOAD_EXPIRED", "上传会话已过期", 409)
    if upload.status not in {
        UploadSessionStatus.UPLOADING,
        UploadSessionStatus.COMPLETING,
    }:
        raise DomainError("UPLOAD_STATE_CONFLICT", "上传会话状态不允许完成", 409)
    if not upload.storage_upload_id:
        raise DomainError(
            "UPLOAD_STATE_CONFLICT", "上传会话缺少远端 Multipart 标识", 409
        )
    registered = list(
        await session.scalars(
            select(UploadPartModel)
            .where(UploadPartModel.upload_session_id == upload.id)
            .order_by(UploadPartModel.part_number)
        )
    )
    expected_parts = [(part.part_number, part.etag) for part in registered]
    submitted_parts = [(part.part_number, part.etag.strip()) for part in payload.parts]
    if (
        submitted_parts != expected_parts
        or sum(part.size_bytes for part in registered) != upload.expected_size
    ):
        raise DomainError("PART_LIST_MISMATCH", "提交的分片清单或总大小不完整", 409)

    if upload.status is UploadSessionStatus.UPLOADING:
        upload.status = UploadSessionStatus.COMPLETING
        await session.commit()
    # Reacquire after the durable COMPLETING checkpoint. Serialize remote
    # verification and final publication, then refresh any concurrent result.
    await set_tenant_context(session, organization_id, current_user.id)
    upload = await session.scalar(
        select(UploadSessionModel)
        .where(UploadSessionModel.id == upload_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert upload is not None
    existing = await session.scalar(
        select(ArtifactModel).where(ArtifactModel.upload_session_id == upload.id)
    )
    if upload.status is UploadSessionStatus.COMPLETED and existing is not None:
        return JSONResponse(
            status_code=200,
            content=ArtifactRead.model_validate(existing).model_dump(mode="json"),
            headers={"Idempotent-Replayed": "true"},
        )
    port = _storage_required(storage)
    completed_parts = [CompletedPart(number, etag) for number, etag in submitted_parts]
    try:
        await port.complete_multipart(
            upload.object_key, upload.storage_upload_id, completed_parts
        )
    except ObjectStorageError as complete_error:
        try:
            await port.head(upload.object_key)
        except ObjectStorageError:
            if complete_error.code is StorageErrorCode.NOT_FOUND:
                raise DomainError(
                    "OBJECT_MISSING", "完成后的对象不存在", 409
                ) from complete_error
            raise _storage_failure(complete_error) from complete_error
    try:
        verification = await verify_object(
            cast(VerificationStoragePort, port), upload.object_key
        )
    except ObjectStorageError as exc:
        if exc.code is StorageErrorCode.NOT_FOUND:
            raise DomainError("OBJECT_MISSING", "完成后的对象不存在", 409) from exc
        raise _storage_failure(exc) from exc

    size_matches = verification.metadata.size_bytes == upload.expected_size
    checksum_matches = verification.verified_sha256 == upload.expected_sha256
    integrity = (
        IntegrityStatus.VERIFIED
        if size_matches and checksum_matches
        else IntegrityStatus.MISMATCH
    )
    artifact_status = (
        ArtifactStatus.AVAILABLE
        if integrity is IntegrityStatus.VERIFIED
        else ArtifactStatus.QUARANTINED
    )
    artifact = ArtifactModel(
        upload_session_id=upload.id,
        organization_id=organization_id,
        project_id=project_id,
        created_by=current_user.id,
        display_name=upload.display_name,
        object_key=upload.object_key,
        bucket_alias="primary",
        size_bytes=verification.metadata.size_bytes,
        expected_sha256=upload.expected_sha256,
        verified_sha256=verification.verified_sha256,
        declared_content_type=upload.declared_content_type,
        detected_content_type=verification.metadata.content_type,
        integrity_status=integrity,
        security_scan_status=SecurityScanStatus.NOT_REQUIRED,
        status=artifact_status,
    )
    session.add(artifact)
    upload.status = UploadSessionStatus.COMPLETED
    upload.completed_at = datetime.now(UTC)
    upload.reserved_bytes = 0
    await session.flush()
    trace_id = getattr(request.state, "trace_id", None)
    detail = {
        "status": artifact.status.value,
        "integrityStatus": integrity.value,
        "sizeBytes": artifact.size_bytes,
    }
    record_audit(
        session,
        actor_id=current_user.id,
        action="upload_session.complete",
        resource_type="artifact",
        resource_id=artifact.id,
        organization_id=organization_id,
        project_id=project_id,
        trace_id=trace_id,
        detail=detail,
    )
    record_outbox(
        session,
        organization_id=organization_id,
        aggregate_type="artifact",
        aggregate_id=artifact.id,
        event_type="ArtifactVerified.v1"
        if integrity is IntegrityStatus.VERIFIED
        else "ArtifactQuarantined.v1",
        aggregate_version=artifact.version,
        trace_id=trace_id,
        payload=detail,
    )
    await session.commit()
    await set_tenant_context(session, organization_id, current_user.id)
    await session.refresh(artifact)
    if not size_matches:
        raise DomainError("SIZE_MISMATCH", "对象大小与上传声明不一致", 409)
    if not checksum_matches:
        raise DomainError("CHECKSUM_MISMATCH", "对象摘要与上传声明不一致", 409)
    return JSONResponse(
        status_code=201,
        content=ArtifactRead.model_validate(artifact).model_dump(mode="json"),
        headers={"Idempotent-Replayed": "false", "ETag": f'"{artifact.version}"'},
    )


@router.post("/{upload_id}:cancel", response_model=UploadSessionRead)
async def cancel_upload_session(
    organization_id: UUID,
    project_id: UUID,
    upload_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
    request: Request,
    storage: Storage,
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
        if upload.storage_upload_id:
            port = _storage_required(storage)
            try:
                await port.abort_multipart(upload.object_key, upload.storage_upload_id)
            except ObjectStorageError as exc:
                raise _storage_failure(exc) from exc
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
        event_type="UploadSessionCancelled.v1"
        if not expired
        else "UploadSessionExpired.v1",
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
