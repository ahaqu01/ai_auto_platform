import hashlib
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from platform_api.api.upload_sessions import get_object_storage
from platform_api.auth.dependencies import get_token_verifier
from platform_api.auth.identity import IdentityClaims
from platform_api.common.errors import DomainError
from platform_api.db.base import Base
from platform_api.db.models import ArtifactModel, UploadSessionModel
from platform_api.db.session import get_session
from platform_api.main import create_app
from platform_api.modules.artifact.storage import (
    ObjectMetadata,
    ObjectStorageError,
    PresignedRequest,
    StorageErrorCode,
)


class FakeTokenVerifier:
    async def verify(self, token: str) -> IdentityClaims:
        if token != "owner-token":
            raise DomainError("AUTHENTICATION_REQUIRED", "invalid", 401)
        return IdentityClaims(
            "https://issuer.test", "owner", "owner@example.com", "Owner"
        )


@dataclass
class FakeStorage:
    content: bytes
    completes: int = 0
    completed_parts: list[tuple[int, str]] = field(default_factory=list)
    complete_error: StorageErrorCode | None = None
    head_error: StorageErrorCode | None = None

    async def start_multipart(self, object_key, content_type, *, cancellation=None):
        return "remote-upload-1"

    async def sign_upload_part(
        self,
        object_key,
        upload_id,
        part_number,
        expires_in_seconds,
        *,
        cancellation=None,
    ):
        return PresignedRequest(
            f"https://storage.test/{part_number}?signature=secret", expires_in_seconds
        )

    async def complete_multipart(
        self, object_key, upload_id, parts, *, cancellation=None
    ):
        self.completes += 1
        self.completed_parts = [(part.part_number, part.etag) for part in parts]
        if self.complete_error:
            raise ObjectStorageError(self.complete_error, "safe", retryable=True)

    async def head(self, object_key, *, cancellation=None):
        if self.head_error:
            raise ObjectStorageError(self.head_error, "safe", retryable=True)
        return ObjectMetadata(len(self.content), "etag", "application/octet-stream")

    async def read_chunks(self, object_key, *, cancellation=None):
        midpoint = len(self.content) // 2
        yield self.content[:midpoint]
        yield self.content[midpoint:]

    async def abort_multipart(self, object_key, upload_id, *, cancellation=None):
        return None


@pytest.fixture
async def completion_api(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'complete.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with factory() as session:
            try:
                yield session
                if session.in_transaction():
                    await session.commit()
            except BaseException:
                if session.in_transaction():
                    await session.rollback()
                raise

    storage = FakeStorage(b"hello-world")
    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_token_verifier] = lambda: FakeTokenVerifier()
    app.dependency_overrides[get_object_storage] = lambda: storage
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, factory, storage
    await engine.dispose()


def headers(key: str | None = None):
    return {
        "Authorization": "Bearer owner-token",
        "Idempotency-Key": key or uuid.uuid4().hex,
    }


async def prepared(
    client: AsyncClient,
    content: bytes,
    expected_sha: str | None = None,
    expected_size: int | None = None,
):
    org = await client.post(
        "/api/v1/organizations", headers=headers(), json={"name": "M2 Org"}
    )
    org_id = org.json()["id"]
    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers=headers(),
        json={"code": uuid.uuid4().hex[:8], "name": "M2 Project"},
    )
    project_id = project.json()["id"]
    upload = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/upload-sessions",
        headers=headers(),
        json={
            "display_name": "data.bin",
            "size_bytes": expected_size or len(content),
            "sha256": expected_sha or hashlib.sha256(content).hexdigest(),
            "content_type": "application/octet-stream",
        },
    )
    base = f"/api/v1/organizations/{org_id}/projects/{project_id}/upload-sessions/{upload.json()['id']}"
    await client.post(
        f"{base}/parts:sign", headers=headers(), json={"part_numbers": [1, 2]}
    )
    first = max(1, (expected_size or len(content)) // 2)
    total = expected_size or len(content)
    await client.put(
        f"{base}/parts/1",
        headers=headers(),
        json={"etag": "etag-1", "size_bytes": first},
    )
    await client.put(
        f"{base}/parts/2",
        headers=headers(),
        json={"etag": "etag-2", "size_bytes": total - first},
    )
    body = {
        "parts": [
            {"part_number": 1, "etag": "etag-1"},
            {"part_number": 2, "etag": "etag-2"},
        ]
    }
    return base, body


@pytest.mark.asyncio
async def test_complete_stream_verifies_and_replays(completion_api):
    client, factory, storage = completion_api
    base, body = await prepared(client, storage.content)
    completed = await client.post(
        f"{base}:complete", headers=headers("complete-idem-key"), json=body
    )
    replay = await client.post(
        f"{base}:complete", headers=headers("complete-idem-key"), json=body
    )
    assert completed.status_code == 201 and completed.json()["status"] == "AVAILABLE"
    assert replay.status_code == 200 and replay.json()["id"] == completed.json()["id"]
    assert storage.completes == 1 and storage.completed_parts == [
        (1, "etag-1"),
        (2, "etag-2"),
    ]
    assert "object_key" not in completed.json()
    async with factory() as session:
        upload = await session.scalar(select(UploadSessionModel))
        artifact = await session.scalar(select(ArtifactModel))
    assert upload.status.value == "COMPLETED" and upload.reserved_bytes == 0
    assert artifact.verified_sha256 == hashlib.sha256(storage.content).hexdigest()


@pytest.mark.asyncio
async def test_lost_complete_response_is_recovered_by_head(completion_api):
    client, factory, storage = completion_api
    base, body = await prepared(client, storage.content)
    storage.complete_error = StorageErrorCode.TIMEOUT
    completed = await client.post(
        f"{base}:complete", headers=headers("lost-response-key"), json=body
    )
    assert completed.status_code == 201 and completed.json()["status"] == "AVAILABLE"
    async with factory() as session:
        assert len(list((await session.scalars(select(ArtifactModel))).all())) == 1


@pytest.mark.asyncio
async def test_transient_complete_and_head_failure_remains_retryable(completion_api):
    client, factory, storage = completion_api
    base, body = await prepared(client, storage.content)
    storage.complete_error = StorageErrorCode.TIMEOUT
    storage.head_error = StorageErrorCode.TIMEOUT
    failed = await client.post(
        f"{base}:complete", headers=headers("first-attempt-key"), json=body
    )
    assert failed.status_code == 503
    async with factory() as session:
        upload = await session.scalar(select(UploadSessionModel))
        assert upload.status.value == "COMPLETING"
        assert await session.scalar(select(ArtifactModel)) is None
    storage.complete_error = None
    storage.head_error = None
    recovered = await client.post(
        f"{base}:complete", headers=headers("retry-attempt-key"), json=body
    )
    assert recovered.status_code == 201 and recovered.json()["status"] == "AVAILABLE"


@pytest.mark.asyncio
async def test_rejects_incomplete_or_reordered_manifest_before_storage(completion_api):
    client, _, storage = completion_api
    base, _ = await prepared(client, storage.content)
    response = await client.post(
        f"{base}:complete",
        headers=headers(),
        json={"parts": [{"part_number": 2, "etag": "etag-2"}]},
    )
    assert (
        response.status_code == 409 and response.json()["code"] == "PART_LIST_MISMATCH"
    )
    assert storage.completes == 0


@pytest.mark.asyncio
async def test_checksum_mismatch_is_quarantined(completion_api):
    client, factory, storage = completion_api
    base, body = await prepared(client, storage.content, expected_sha="0" * 64)
    response = await client.post(f"{base}:complete", headers=headers(), json=body)
    assert (
        response.status_code == 409 and response.json()["code"] == "CHECKSUM_MISMATCH"
    )
    async with factory() as session:
        artifact = await session.scalar(select(ArtifactModel))
    assert (
        artifact.status.value == "QUARANTINED"
        and artifact.integrity_status.value == "MISMATCH"
    )


@pytest.mark.asyncio
async def test_size_mismatch_is_quarantined(completion_api):
    client, factory, storage = completion_api
    base, body = await prepared(
        client, storage.content, expected_size=len(storage.content) + 1
    )
    response = await client.post(f"{base}:complete", headers=headers(), json=body)
    assert response.status_code == 409 and response.json()["code"] == "SIZE_MISMATCH"
    async with factory() as session:
        artifact = await session.scalar(select(ArtifactModel))
    assert artifact.status.value == "QUARANTINED"
