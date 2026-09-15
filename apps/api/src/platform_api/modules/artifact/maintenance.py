from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_api.common.reliability import record_outbox
from platform_api.db.models import ArtifactModel, AuditEventModel, UploadSessionModel
from platform_api.modules.artifact.domain import ArtifactStatus, UploadSessionStatus
from platform_api.modules.artifact.storage import (
    ObjectStorageError,
    ObjectStoragePort,
    StorageErrorCode,
)

logger = logging.getLogger(__name__)
_SYSTEM_ACTOR = UUID(int=0)
_OBJECT_KEY = re.compile(r"^v1/o/[0-9a-f]{32}$")
_ACTIVE_UPLOADS = {
    UploadSessionStatus.PENDING_UPLOAD,
    UploadSessionStatus.UPLOADING,
    UploadSessionStatus.COMPLETING,
}


@dataclass(slots=True)
class MaintenanceMetrics:
    expired_sessions: int = 0
    multipart_aborted: int = 0
    artifacts_deleted: int = 0
    missing_objects: int = 0
    orphan_objects_deleted: int = 0
    failures: int = 0


class ArtifactMaintenanceService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage: ObjectStoragePort,
        *,
        batch_size: int = 100,
        orphan_grace: timedelta = timedelta(hours=24),
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not 1 <= batch_size <= 1000:
            raise ValueError("batch_size must be between 1 and 1000")
        if orphan_grace < timedelta():
            raise ValueError("orphan_grace must not be negative")
        self._sessions = session_factory
        self._storage = storage
        self._batch_size = batch_size
        self._orphan_grace = orphan_grace
        self._now = now or (lambda: datetime.now(UTC))

    async def run_once(self) -> MaintenanceMetrics:
        metrics = MaintenanceMetrics()
        await self._expire_sessions(metrics)
        await self._delete_artifacts(metrics)
        await self._reconcile_missing(metrics)
        await self._delete_orphans(metrics)
        logger.info("artifact_maintenance_completed", extra=asdict(metrics))
        return metrics

    async def _expire_sessions(self, metrics: MaintenanceMetrics) -> None:
        now = self._now()
        async with self._sessions() as db:
            rows = list(
                (
                    await db.scalars(
                        select(UploadSessionModel)
                        .where(
                            or_(
                                and_(
                                    UploadSessionModel.status.in_(_ACTIVE_UPLOADS),
                                    UploadSessionModel.expires_at <= now,
                                ),
                                and_(
                                    UploadSessionModel.status
                                    == UploadSessionStatus.EXPIRED,
                                    UploadSessionModel.storage_upload_id.is_not(None),
                                ),
                            ),
                            or_(
                                UploadSessionModel.cleanup_next_attempt_at.is_(None),
                                UploadSessionModel.cleanup_next_attempt_at <= now,
                            ),
                        )
                        .order_by(UploadSessionModel.expires_at, UploadSessionModel.id)
                        .limit(self._batch_size)
                    )
                ).all()
            )
            work: list[tuple[UUID, str, str]] = []
            for row in rows:
                if row.status in _ACTIVE_UPLOADS:
                    row.status = UploadSessionStatus.EXPIRED
                    row.reserved_bytes = 0
                    metrics.expired_sessions += 1
                    self._events(
                        db,
                        row.organization_id,
                        row.project_id,
                        row.id,
                        row.version + 1,
                        "UploadSessionExpired.v1",
                        "UPLOAD_SESSION_EXPIRED",
                    )
                if row.storage_upload_id:
                    work.append((row.id, row.object_key, row.storage_upload_id))
            await db.commit()
        for row_id, key, upload_id in work:
            try:
                await self._storage.abort_multipart(key, upload_id)
            except ObjectStorageError as exc:
                if exc.code != StorageErrorCode.NOT_FOUND:
                    metrics.failures += 1
                    await self._record_upload_failure(row_id, exc.code, now)
                    continue
            async with self._sessions() as db:
                row = await db.get(UploadSessionModel, row_id)
                if row and row.storage_upload_id == upload_id:
                    row.storage_upload_id = None
                    row.cleanup_attempts = 0
                    row.cleanup_last_error = None
                    row.cleanup_next_attempt_at = None
                    metrics.multipart_aborted += 1
                    await db.commit()

    async def _delete_artifacts(self, metrics: MaintenanceMetrics) -> None:
        now = self._now()
        async with self._sessions() as db:
            rows = list(
                (
                    await db.scalars(
                        select(ArtifactModel)
                        .where(
                            ArtifactModel.status == ArtifactStatus.DELETING,
                            or_(
                                ArtifactModel.cleanup_next_attempt_at.is_(None),
                                ArtifactModel.cleanup_next_attempt_at <= now,
                            ),
                        )
                        .order_by(ArtifactModel.updated_at, ArtifactModel.id)
                        .limit(self._batch_size)
                    )
                ).all()
            )
            work = [(x.id, x.object_key) for x in rows]
        for row_id, key in work:
            try:
                await self._storage.delete(key)
            except ObjectStorageError as exc:
                if exc.code != StorageErrorCode.NOT_FOUND:
                    metrics.failures += 1
                    await self._record_artifact_failure(row_id, exc.code, now)
                    continue
            async with self._sessions() as db:
                row = await db.get(ArtifactModel, row_id)
                if row and row.status == ArtifactStatus.DELETING:
                    row.status = ArtifactStatus.DELETED
                    row.deleted_at = now
                    row.cleanup_attempts = 0
                    row.cleanup_last_error = None
                    row.cleanup_next_attempt_at = None
                    metrics.artifacts_deleted += 1
                    self._events(
                        db,
                        row.organization_id,
                        row.project_id,
                        row.id,
                        row.version + 1,
                        "ArtifactDeleted.v1",
                        "ARTIFACT_DELETED",
                    )
                    await db.commit()

    async def _reconcile_missing(self, metrics: MaintenanceMetrics) -> None:
        async with self._sessions() as db:
            rows = list(
                (
                    await db.scalars(
                        select(ArtifactModel)
                        .where(ArtifactModel.status == ArtifactStatus.AVAILABLE)
                        .order_by(ArtifactModel.updated_at, ArtifactModel.id)
                        .limit(self._batch_size)
                    )
                ).all()
            )
            work = [(x.id, x.object_key) for x in rows]
        for row_id, key in work:
            try:
                await self._storage.head(key)
                continue
            except ObjectStorageError as exc:
                if exc.code != StorageErrorCode.NOT_FOUND:
                    metrics.failures += 1
                    continue
            async with self._sessions() as db:
                row = await db.get(ArtifactModel, row_id)
                if row and row.status == ArtifactStatus.AVAILABLE:
                    row.status = ArtifactStatus.FAILED
                    metrics.missing_objects += 1
                    self._events(
                        db,
                        row.organization_id,
                        row.project_id,
                        row.id,
                        row.version + 1,
                        "ArtifactObjectMissing.v1",
                        "ARTIFACT_OBJECT_MISSING",
                    )
                    await db.commit()

    async def _delete_orphans(self, metrics: MaintenanceMetrics) -> None:
        cutoff = self._now() - self._orphan_grace
        seen = 0
        async for item in self._storage.list_objects("v1/o/"):
            if seen >= self._batch_size:
                break
            if item.last_modified > cutoff or not _OBJECT_KEY.fullmatch(
                item.object_key
            ):
                continue
            seen += 1
            async with self._sessions() as db:
                known_upload = await db.scalar(
                    select(UploadSessionModel.id)
                    .where(UploadSessionModel.object_key == item.object_key)
                    .limit(1)
                )
                known_artifact = await db.scalar(
                    select(ArtifactModel.id)
                    .where(
                        ArtifactModel.object_key == item.object_key,
                        ArtifactModel.status != ArtifactStatus.DELETED,
                    )
                    .limit(1)
                )
            if known_upload or known_artifact:
                continue
            deleted = False
            try:
                await self._storage.delete(item.object_key)
                deleted = True
            except ObjectStorageError as exc:
                if exc.code == StorageErrorCode.NOT_FOUND:
                    deleted = True
                else:
                    metrics.failures += 1
            if deleted:
                metrics.orphan_objects_deleted += 1
                resource_id = uuid5(NAMESPACE_URL, item.object_key)
                async with self._sessions() as db:
                    self._events(
                        db,
                        None,
                        None,
                        resource_id,
                        1,
                        "ArtifactOrphanDeleted.v1",
                        "ARTIFACT_ORPHAN_DELETED",
                    )
                    await db.commit()

    async def _record_upload_failure(
        self, row_id: UUID, code: StorageErrorCode, now: datetime
    ) -> None:
        async with self._sessions() as db:
            row = await db.get(UploadSessionModel, row_id)
            if row:
                row.cleanup_attempts += 1
                row.cleanup_last_error = code.value
                row.cleanup_next_attempt_at = now + self._backoff(row.cleanup_attempts)
                await db.commit()

    async def _record_artifact_failure(
        self, row_id: UUID, code: StorageErrorCode, now: datetime
    ) -> None:
        async with self._sessions() as db:
            row = await db.get(ArtifactModel, row_id)
            if row:
                row.cleanup_attempts += 1
                row.cleanup_last_error = code.value
                row.cleanup_next_attempt_at = now + self._backoff(row.cleanup_attempts)
                await db.commit()

    @staticmethod
    def _backoff(attempts: int) -> timedelta:
        return timedelta(seconds=min(3600, 30 * (2 ** min(attempts - 1, 7))))

    @staticmethod
    def _events(
        db: AsyncSession,
        org_id: UUID | None,
        project_id: UUID | None,
        resource_id: UUID,
        version: int,
        event_type: str,
        action: str,
    ) -> None:
        db.add(
            AuditEventModel(
                organization_id=org_id,
                project_id=project_id,
                actor_type="SYSTEM",
                actor_id=_SYSTEM_ACTOR,
                action=action,
                resource_type="artifact_maintenance",
                resource_id=resource_id,
                result="SUCCESS",
                detail={},
            )
        )
        record_outbox(
            db,
            organization_id=org_id,
            aggregate_type="artifact",
            aggregate_id=resource_id,
            event_type=event_type,
            trace_id=None,
            aggregate_version=version,
        )
