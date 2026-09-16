from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import PurePath
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_api.api.upload_sessions import _authorized_project, get_object_storage
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
from platform_api.db.models import ArtifactModel
from platform_api.db.session import get_session
from platform_api.modules.artifact.domain import (
    ArtifactStatus,
    IntegrityStatus,
    SecurityScanStatus,
)
from platform_api.modules.artifact.storage import ObjectStorageError, ObjectStoragePort

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/projects/{project_id}/artifacts",
    tags=["artifacts"],
    responses=PROTECTED_ERROR_RESPONSES,
)
DbSession = Annotated[AsyncSession, Depends(get_session)]
Storage = Annotated[ObjectStoragePort | None, Depends(get_object_storage)]


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


class ArtifactPage(StrictModel):
    items: list[ArtifactRead]
    next_cursor: str | None


class DownloadUrlRequest(StrictModel):
    expires_in_seconds: int = Field(default=600, ge=60, le=3600)


class DownloadUrlRead(StrictModel):
    url: str
    expires_in_seconds: int
    content_disposition: str


def _encode_cursor(artifact: ArtifactModel) -> str:
    raw = json.dumps(
        [artifact.created_at.isoformat(), str(artifact.id)], separators=(",", ":")
    ).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        created_at, artifact_id = json.loads(raw)
        return datetime.fromisoformat(created_at), UUID(artifact_id)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise DomainError("INVALID_CURSOR", "分页游标无效", 400) from exc


def _version(if_match: str | None) -> int:
    if if_match is None:
        raise DomainError("IF_MATCH_REQUIRED", "删除资产必须提供 If-Match", 428)
    value = if_match.strip().removeprefix("W/")
    if len(value) < 3 or value[0] != '"' or value[-1] != '"':
        raise DomainError("INVALID_IF_MATCH", "If-Match 必须是带引号的整数版本", 400)
    try:
        return int(value[1:-1])
    except ValueError as exc:
        raise DomainError(
            "INVALID_IF_MATCH", "If-Match 必须是带引号的整数版本", 400
        ) from exc


def _safe_download_name(value: str) -> str:
    name = PurePath(value.replace("\\", "/")).name.replace('"', "_").strip()
    return (name or "artifact.bin")[:255]


async def _visible_artifact(
    session: AsyncSession,
    organization_id: UUID,
    project_id: UUID,
    artifact_id: UUID,
    actor_id: UUID,
    *,
    write: bool,
) -> ArtifactModel:
    await _authorized_project(
        session, organization_id, project_id, actor_id, write=write
    )
    artifact = await session.scalar(
        select(ArtifactModel).where(
            ArtifactModel.id == artifact_id,
            ArtifactModel.organization_id == organization_id,
            ArtifactModel.project_id == project_id,
        )
    )
    if artifact is None:
        raise DomainError("ARTIFACT_NOT_FOUND", "资产不存在或无权访问", 404)
    return artifact


@router.get("", response_model=ArtifactPage)
async def list_artifacts(
    organization_id: UUID,
    project_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=500)] = None,
):
    await _authorized_project(
        session, organization_id, project_id, current_user.id, write=False
    )
    statement = select(ArtifactModel).where(
        ArtifactModel.organization_id == organization_id,
        ArtifactModel.project_id == project_id,
        ArtifactModel.status.notin_({ArtifactStatus.DELETING, ArtifactStatus.DELETED}),
    )
    if cursor:
        created_at, artifact_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                ArtifactModel.created_at < created_at,
                and_(
                    ArtifactModel.created_at == created_at,
                    ArtifactModel.id < artifact_id,
                ),
            )
        )
    rows = list(
        await session.scalars(
            statement.order_by(
                ArtifactModel.created_at.desc(), ArtifactModel.id.desc()
            ).limit(limit + 1)
        )
    )
    items = rows[:limit]
    return ArtifactPage(
        items=[ArtifactRead.model_validate(item) for item in items],
        next_cursor=_encode_cursor(items[-1]) if len(rows) > limit else None,
    )


@router.get("/{artifact_id}", response_model=ArtifactRead)
async def get_artifact(
    organization_id: UUID,
    project_id: UUID,
    artifact_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
):
    artifact = await _visible_artifact(
        session, organization_id, project_id, artifact_id, current_user.id, write=False
    )
    if artifact.status in {ArtifactStatus.DELETING, ArtifactStatus.DELETED}:
        raise DomainError("ARTIFACT_NOT_FOUND", "资产不存在或无权访问", 404)
    return JSONResponse(
        content=ArtifactRead.model_validate(artifact).model_dump(mode="json"),
        headers={"ETag": f'"{artifact.version}"'},
    )


@router.post("/{artifact_id}:download-url", response_model=DownloadUrlRead)
async def create_download_url(
    organization_id: UUID,
    project_id: UUID,
    artifact_id: UUID,
    payload: DownloadUrlRequest,
    current_user: CurrentUser,
    session: DbSession,
    storage: Storage,
):
    artifact = await _visible_artifact(
        session, organization_id, project_id, artifact_id, current_user.id, write=False
    )
    if artifact.status is not ArtifactStatus.AVAILABLE:
        raise DomainError("ARTIFACT_NOT_AVAILABLE", "资产当前不可下载", 409)
    if storage is None:
        raise DomainError("STORAGE_UNAVAILABLE", "对象存储运行时尚未配置", 503)
    filename = _safe_download_name(artifact.display_name)
    try:
        signed = await storage.sign_download(
            artifact.object_key, payload.expires_in_seconds, filename
        )
    except ObjectStorageError as exc:
        raise DomainError("STORAGE_UNAVAILABLE", "对象存储暂时不可用", 503) from exc
    disposition = f"attachment; filename*=UTF-8''{quote(filename, safe='')}"
    return DownloadUrlRead(
        url=signed.url,
        expires_in_seconds=signed.expires_in_seconds,
        content_disposition=disposition,
    )


@router.delete("/{artifact_id}", response_model=ArtifactRead)
async def delete_artifact(
    organization_id: UUID,
    project_id: UUID,
    artifact_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
    request: Request,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    artifact = await _visible_artifact(
        session, organization_id, project_id, artifact_id, current_user.id, write=True
    )
    decision = await begin_idempotent_command(
        session,
        actor_id=current_user.id,
        route_key=f"artifacts.{artifact_id}.delete",
        idempotency_key=idempotency_key,
        request_payload={"artifactId": str(artifact_id)},
    )
    if decision.is_replay:
        return JSONResponse(
            status_code=decision.replay_status,
            content=decision.replay_body,
            headers={"Idempotent-Replayed": "true"},
        )
    if artifact.version != _version(if_match):
        raise DomainError("VERSION_MISMATCH", "资产版本已变化，请刷新后重试", 412)
    if artifact.status is ArtifactStatus.DELETED:
        raise DomainError("ARTIFACT_NOT_FOUND", "资产不存在或无权访问", 404)
    artifact.status = ArtifactStatus.DELETING
    await session.flush()
    await session.refresh(artifact)
    trace_id = getattr(request.state, "trace_id", None)
    detail = {"status": artifact.status.value}
    record_audit(
        session,
        actor_id=current_user.id,
        action="artifact.delete.request",
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
        event_type="ArtifactDeletionRequested.v1",
        aggregate_version=artifact.version,
        trace_id=trace_id,
        payload=detail,
    )
    body = ArtifactRead.model_validate(artifact).model_dump(mode="json")
    complete_idempotent_command(decision, response_status=200, response_body=body)
    await session.commit()
    return JSONResponse(
        status_code=200,
        content=body,
        headers={"Idempotent-Replayed": "false", "ETag": f'"{artifact.version}"'},
    )
