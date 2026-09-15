from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from platform_api.db.base import Base
from platform_api.db.models import (
    ArtifactModel,
    AuditEventModel,
    OrganizationModel,
    OutboxEventModel,
    ProjectModel,
    UploadSessionModel,
    UserModel,
)
from platform_api.modules.artifact.domain import (
    ArtifactStatus,
    IntegrityStatus,
    SecurityScanStatus,
    UploadSessionStatus,
)
from platform_api.modules.artifact.maintenance import ArtifactMaintenanceService
from platform_api.modules.artifact.storage import (
    ObjectMetadata,
    ObjectStorageError,
    StorageErrorCode,
    StorageObjectRef,
)


class FakeStorage:
    def __init__(self, now):
        self.now = now
        self.aborted = []
        self.deleted = []
        self.abort_error = None
        self.delete_errors = {}
        self.missing = set()
        self.head_errors = set()
        self.objects = []

    async def abort_multipart(self, key, upload_id, *, cancellation=None):
        if self.abort_error:
            raise ObjectStorageError(self.abort_error, "safe", retryable=True)
        self.aborted.append((key, upload_id))

    async def delete(self, key, *, cancellation=None):
        if key in self.delete_errors:
            raise ObjectStorageError(self.delete_errors[key], "safe", retryable=True)
        self.deleted.append(key)

    async def head(self, key, *, cancellation=None):
        if key in self.missing:
            raise ObjectStorageError(
                StorageErrorCode.NOT_FOUND, "safe", retryable=False
            )
        if key in self.head_errors:
            raise ObjectStorageError(StorageErrorCode.TIMEOUT, "safe", retryable=True)
        return ObjectMetadata(1, "e", "application/octet-stream")

    async def list_objects(self, prefix, *, cancellation=None):
        for item in self.objects:
            yield item


@pytest.fixture
async def setup(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'm207.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    now = datetime(2026, 9, 15, 12, tzinfo=UTC)
    ids = {name: uuid4() for name in ("user", "org", "project")}
    async with factory() as db:
        db.add(
            UserModel(id=ids["user"], email="owner@example.test", display_name="Owner")
        )
        db.add(OrganizationModel(id=ids["org"], name="Org"))
        db.add(
            ProjectModel(
                id=ids["project"], organization_id=ids["org"], code="p", name="P"
            )
        )
        await db.commit()
    storage = FakeStorage(now)
    yield factory, storage, now, ids
    await engine.dispose()


def upload(
    ids, now, key, *, status=UploadSessionStatus.COMPLETED, expired=False, remote=None
):
    return UploadSessionModel(
        id=uuid4(),
        organization_id=ids["org"],
        project_id=ids["project"],
        created_by=ids["user"],
        display_name="x.bin",
        object_key=key,
        expected_size=1,
        expected_sha256="0" * 64,
        declared_content_type="application/octet-stream",
        status=status,
        storage_upload_id=remote,
        reserved_bytes=1 if status != UploadSessionStatus.COMPLETED else 0,
        expires_at=now - timedelta(minutes=1) if expired else now + timedelta(days=1),
    )


def artifact(ids, up, key, status):
    return ArtifactModel(
        id=uuid4(),
        upload_session_id=up.id,
        organization_id=ids["org"],
        project_id=ids["project"],
        created_by=ids["user"],
        display_name="x.bin",
        object_key=key,
        bucket_alias="primary",
        size_bytes=1,
        expected_sha256="0" * 64,
        verified_sha256="0" * 64,
        declared_content_type="application/octet-stream",
        detected_content_type="application/octet-stream",
        integrity_status=IntegrityStatus.VERIFIED,
        security_scan_status=SecurityScanStatus.NOT_REQUIRED,
        status=status,
    )


@pytest.mark.asyncio
async def test_run_once_reconciles_all_safe_paths(setup):
    factory, storage, now, ids = setup
    exp_key = "v1/o/" + "1" * 32
    del_key = "v1/o/" + "2" * 32
    miss_key = "v1/o/" + "3" * 32
    known_key = "v1/o/" + "4" * 32
    orphan_key = "v1/o/" + "5" * 32
    young_key = "v1/o/" + "6" * 32
    expired = upload(
        ids,
        now,
        exp_key,
        status=UploadSessionStatus.UPLOADING,
        expired=True,
        remote="remote-id",
    )
    deleting_up = upload(ids, now, del_key)
    missing_up = upload(ids, now, miss_key)
    known_up = upload(ids, now, known_key)
    async with factory() as db:
        db.add_all([expired, deleting_up, missing_up, known_up])
        db.add_all(
            [
                artifact(ids, deleting_up, del_key, ArtifactStatus.DELETING),
                artifact(ids, missing_up, miss_key, ArtifactStatus.AVAILABLE),
                artifact(ids, known_up, known_key, ArtifactStatus.AVAILABLE),
            ]
        )
        await db.commit()
    storage.missing.add(miss_key)
    storage.objects = [
        StorageObjectRef(orphan_key, now - timedelta(days=2)),
        StorageObjectRef(young_key, now),
        StorageObjectRef(known_key, now - timedelta(days=2)),
        StorageObjectRef("unsafe/key", now - timedelta(days=2)),
    ]
    metrics = await ArtifactMaintenanceService(
        factory, storage, now=lambda: now
    ).run_once()
    assert (
        metrics.expired_sessions,
        metrics.multipart_aborted,
        metrics.artifacts_deleted,
        metrics.missing_objects,
        metrics.orphan_objects_deleted,
        metrics.failures,
    ) == (1, 1, 1, 1, 1, 0)
    assert storage.aborted == [(exp_key, "remote-id")]
    assert del_key in storage.deleted and orphan_key in storage.deleted
    assert young_key not in storage.deleted and known_key not in storage.deleted
    async with factory() as db:
        expired_db = await db.get(UploadSessionModel, expired.id)
        deleted_db = await db.scalar(
            select(ArtifactModel).where(ArtifactModel.object_key == del_key)
        )
        missing_db = await db.scalar(
            select(ArtifactModel).where(ArtifactModel.object_key == miss_key)
        )
        audits = list((await db.scalars(select(AuditEventModel))).all())
        outbox = list((await db.scalars(select(OutboxEventModel))).all())
    assert (
        expired_db.status == UploadSessionStatus.EXPIRED
        and expired_db.reserved_bytes == 0
        and expired_db.storage_upload_id is None
    )
    assert (
        deleted_db.status == ArtifactStatus.DELETED
        and deleted_db.deleted_at.replace(tzinfo=UTC) == now
    )
    assert missing_db.status == ArtifactStatus.FAILED
    assert (
        len(audits) == 4
        and len(outbox) == 4
        and all(x.actor_type == "SYSTEM" for x in audits)
    )


@pytest.mark.asyncio
async def test_failures_are_safe_retryable_and_not_false_success(setup):
    factory, storage, now, ids = setup
    exp_key = "v1/o/" + "a" * 32
    del_key = "v1/o/" + "b" * 32
    head_key = "v1/o/" + "c" * 32
    expired = upload(
        ids,
        now,
        exp_key,
        status=UploadSessionStatus.UPLOADING,
        expired=True,
        remote="secret-upload-id",
    )
    deleting_up = upload(ids, now, del_key)
    head_up = upload(ids, now, head_key)
    deleting = artifact(ids, deleting_up, del_key, ArtifactStatus.DELETING)
    available = artifact(ids, head_up, head_key, ArtifactStatus.AVAILABLE)
    async with factory() as db:
        db.add_all([expired, deleting_up, head_up, deleting, available])
        await db.commit()
    storage.abort_error = StorageErrorCode.TEMPORARY_UNAVAILABLE
    storage.delete_errors[del_key] = StorageErrorCode.ACCESS_DENIED
    storage.head_errors.add(head_key)
    metrics = await ArtifactMaintenanceService(
        factory, storage, now=lambda: now
    ).run_once()
    assert (
        metrics.failures == 3
        and metrics.multipart_aborted == 0
        and metrics.artifacts_deleted == 0
        and metrics.missing_objects == 0
    )
    async with factory() as db:
        expired_db = await db.get(UploadSessionModel, expired.id)
        deleting_db = await db.get(ArtifactModel, deleting.id)
        available_db = await db.get(ArtifactModel, available.id)
    assert expired_db.storage_upload_id == "secret-upload-id"
    assert (
        expired_db.cleanup_attempts == 1
        and expired_db.cleanup_last_error == "TEMPORARY_UNAVAILABLE"
        and expired_db.cleanup_next_attempt_at.replace(tzinfo=UTC)
        == now + timedelta(seconds=30)
    )
    assert (
        deleting_db.status == ArtifactStatus.DELETING
        and deleting_db.cleanup_last_error == "ACCESS_DENIED"
    )
    assert available_db.status == ArtifactStatus.AVAILABLE


@pytest.mark.asyncio
async def test_not_found_delete_and_abort_are_idempotent_success(setup):
    factory, storage, now, ids = setup
    exp_key = "v1/o/" + "d" * 32
    del_key = "v1/o/" + "e" * 32
    expired = upload(
        ids,
        now,
        exp_key,
        status=UploadSessionStatus.EXPIRED,
        expired=True,
        remote="gone",
    )
    deleting_up = upload(ids, now, del_key)
    deleting = artifact(ids, deleting_up, del_key, ArtifactStatus.DELETING)
    async with factory() as db:
        db.add_all([expired, deleting_up, deleting])
        await db.commit()
    storage.abort_error = StorageErrorCode.NOT_FOUND
    storage.delete_errors[del_key] = StorageErrorCode.NOT_FOUND
    metrics = await ArtifactMaintenanceService(
        factory, storage, now=lambda: now
    ).run_once()
    assert (
        metrics.multipart_aborted == 1
        and metrics.artifacts_deleted == 1
        and metrics.failures == 0
    )


def test_configuration_bounds(setup):
    factory, storage, _, _ = setup
    with pytest.raises(ValueError):
        ArtifactMaintenanceService(factory, storage, batch_size=0)
    with pytest.raises(ValueError):
        ArtifactMaintenanceService(factory, storage, orphan_grace=timedelta(seconds=-1))
