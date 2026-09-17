import uuid
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from platform_api.api.upload_sessions import get_object_storage
from platform_api.auth.dependencies import get_token_verifier
from platform_api.auth.identity import IdentityClaims
from platform_api.common.errors import DomainError
from platform_api.db.base import Base
from platform_api.db.session import get_session
from platform_api.main import create_app
from platform_api.modules.artifact.storage import (
    ObjectStorageError,
    PresignedRequest,
    StorageErrorCode,
)


@dataclass
class FakeTokenVerifier:
    async def verify(self, token: str) -> IdentityClaims:
        if token != "owner-token":
            raise DomainError("AUTHENTICATION_REQUIRED", "invalid", 401)
        return IdentityClaims(
            "https://issuer.test", "owner", "owner@example.com", "Owner"
        )


@dataclass
class FakeStorage:
    starts: int = 0
    signed: list[int] = field(default_factory=list)
    aborted: list[str] = field(default_factory=list)
    sign_error: StorageErrorCode | None = None

    async def start_multipart(self, object_key, content_type, *, cancellation=None):
        self.starts += 1
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
        self.signed.append(part_number)
        if self.sign_error:
            raise ObjectStorageError(self.sign_error, "safe", retryable=True)
        return PresignedRequest(
            f"https://storage.test/{part_number}?signature=secret", expires_in_seconds
        )

    async def abort_multipart(self, object_key, upload_id, *, cancellation=None):
        self.aborted.append(upload_id)


@pytest.fixture
async def multipart_api(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'multipart.db'}")
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

    storage = FakeStorage()
    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_token_verifier] = lambda: FakeTokenVerifier()
    app.dependency_overrides[get_object_storage] = lambda: storage
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, storage
    await engine.dispose()


def headers() -> dict[str, str]:
    return {"Authorization": "Bearer owner-token", "Idempotency-Key": uuid.uuid4().hex}


async def create_upload(client: AsyncClient):
    org = await client.post(
        "/api/v1/organizations", headers=headers(), json={"name": "M2 Org"}
    )
    org_id = org.json()["id"]
    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers=headers(),
        json={"code": uuid.uuid4().hex[:10], "name": "M2 Project"},
    )
    project_id = project.json()["id"]
    upload = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/upload-sessions",
        headers=headers(),
        json={
            "display_name": "data.bin",
            "size_bytes": 1000,
            "sha256": "a" * 64,
            "content_type": "application/octet-stream",
        },
    )
    base = f"/api/v1/organizations/{org_id}/projects/{project_id}/upload-sessions/{upload.json()['id']}"
    return base


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ttl,expected", [(59, 422), (60, 200), (900, 200), (901, 422), (3600, 422)]
)
async def test_upload_signing_ttl_contract(multipart_api, ttl, expected):
    client, storage = multipart_api
    base = await create_upload(client)
    response = await client.post(
        f"{base}/parts:sign",
        headers=headers(),
        json={"part_numbers": [1], "expires_in_seconds": ttl},
    )
    assert response.status_code == expected
    if expected == 200:
        assert response.json()[0]["expires_in_seconds"] == ttl
    else:
        assert storage.starts == 0


@pytest.mark.asyncio
async def test_sign_initializes_once_and_never_exposes_remote_upload_id(multipart_api):
    client, storage = multipart_api
    base = await create_upload(client)
    first = await client.post(
        f"{base}/parts:sign", headers=headers(), json={"part_numbers": [1, 2]}
    )
    second = await client.post(
        f"{base}/parts:sign", headers=headers(), json={"part_numbers": [2]}
    )
    assert first.status_code == second.status_code == 200
    assert [part["part_number"] for part in first.json()] == [1, 2]
    assert storage.starts == 1
    session = await client.get(base, headers=headers())
    assert session.json()["status"] == "UPLOADING"
    assert "storage_upload_id" not in session.json()


@pytest.mark.asyncio
async def test_register_replay_resume_and_conflict(multipart_api):
    client, _ = multipart_api
    base = await create_upload(client)
    await client.post(
        f"{base}/parts:sign", headers=headers(), json={"part_numbers": [2, 1]}
    )
    body = {"etag": '"etag-1"', "size_bytes": 500}
    created = await client.put(f"{base}/parts/1", headers=headers(), json=body)
    replay = await client.put(f"{base}/parts/1", headers=headers(), json=body)
    conflict = await client.put(
        f"{base}/parts/1",
        headers=headers(),
        json={"etag": '"other"', "size_bytes": 500},
    )
    resume = await client.get(f"{base}/parts", headers=headers())
    assert created.status_code == replay.status_code == 200
    assert (
        conflict.status_code == 409
        and conflict.json()["code"] == "UPLOAD_PART_CONFLICT"
    )
    assert [part["part_number"] for part in resume.json()] == [1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [StorageErrorCode.TIMEOUT, StorageErrorCode.TEMPORARY_UNAVAILABLE]
)
async def test_sign_failure_keeps_remote_multipart_resumable(multipart_api, failure):
    client, storage = multipart_api
    base = await create_upload(client)
    storage.sign_error = failure
    failed = await client.post(
        f"{base}/parts:sign", headers=headers(), json={"part_numbers": [1]}
    )
    assert failed.status_code == 503
    storage.sign_error = None
    resumed = await client.post(
        f"{base}/parts:sign", headers=headers(), json={"part_numbers": [1]}
    )
    assert resumed.status_code == 200 and storage.starts == 1
    session = await client.get(base, headers=headers())
    assert session.json()["status"] == "UPLOADING"


@pytest.mark.asyncio
async def test_validation_state_and_remote_abort(multipart_api):
    client, storage = multipart_api
    base = await create_upload(client)
    duplicate = await client.post(
        f"{base}/parts:sign", headers=headers(), json={"part_numbers": [1, 1]}
    )
    invalid = await client.post(
        f"{base}/parts:sign", headers=headers(), json={"part_numbers": [10001]}
    )
    await client.post(
        f"{base}/parts:sign", headers=headers(), json={"part_numbers": [1]}
    )
    cancelled = await client.post(f"{base}:cancel", headers=headers())
    after_cancel = await client.put(
        f"{base}/parts/1", headers=headers(), json={"etag": "x", "size_bytes": 1}
    )
    assert duplicate.status_code == invalid.status_code == 422
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "ABORTED"
    assert storage.aborted == ["remote-upload-1"]
    assert after_cancel.status_code == 409


@pytest.mark.asyncio
async def test_missing_runtime_fails_closed(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'closed.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_token_verifier] = lambda: FakeTokenVerifier()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        base = await create_upload(client)
        response = await client.post(
            f"{base}/parts:sign", headers=headers(), json={"part_numbers": [1]}
        )
    await engine.dispose()
    assert (
        response.status_code == 503 and response.json()["code"] == "STORAGE_UNAVAILABLE"
    )
