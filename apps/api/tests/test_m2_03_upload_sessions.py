import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from platform_api.auth.dependencies import get_token_verifier
from platform_api.auth.identity import IdentityClaims
from platform_api.common.errors import DomainError
from platform_api.db.base import Base
from platform_api.db.models import UploadSessionModel
from platform_api.db.session import get_session
from platform_api.main import create_app
from platform_api.modules.artifact.domain import UploadSessionStatus


@dataclass
class FakeTokenVerifier:
    async def verify(self, token: str) -> IdentityClaims:
        identities = {
            "owner-token": IdentityClaims("https://issuer.test", "owner", "owner@example.com", "Owner"),
            "outsider-token": IdentityClaims("https://issuer.test", "outsider", "out@example.com", "Outsider"),
        }
        try:
            return identities[token]
        except KeyError as exc:
            raise DomainError("AUTHENTICATION_REQUIRED", "身份凭证无效", 401) from exc


@pytest.fixture
async def upload_api(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'upload.db'}")
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

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_token_verifier] = lambda: FakeTokenVerifier()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, factory
    await engine.dispose()


def headers(token: str = "owner-token", key: str | None = None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": key or uuid.uuid4().hex,
    }


async def create_project(client: AsyncClient) -> tuple[str, str]:
    organization = await client.post("/api/v1/organizations", headers=headers(), json={"name": "M2 Org"})
    organization_id = organization.json()["id"]
    project = await client.post(
        f"/api/v1/organizations/{organization_id}/projects",
        headers=headers(),
        json={"code": f"m2-{uuid.uuid4().hex[:8]}", "name": "M2 Project"},
    )
    return organization_id, project.json()["id"]


def payload(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "display_name": "dataset.zip",
        "size_bytes": 1024,
        "sha256": "a" * 64,
        "content_type": "application/zip",
    }
    values.update(overrides)
    return values


@pytest.mark.asyncio
async def test_create_generates_opaque_key_and_same_transaction_events(upload_api) -> None:
    client, factory = upload_api
    organization_id, project_id = await create_project(client)
    response = await client.post(
        f"/api/v1/organizations/{organization_id}/projects/{project_id}/upload-sessions",
        headers=headers(),
        json=payload(),
    )
    assert response.status_code == 201
    assert response.json()["status"] == "PENDING_UPLOAD"
    assert "object_key" not in response.json()
    async with factory() as session:
        upload = await session.scalar(select(UploadSessionModel))
    assert upload is not None
    assert re.fullmatch(r"v1/o/[0-9a-f]{32}", upload.object_key)
    assert "dataset" not in upload.object_key
    assert upload.reserved_bytes == 1024


@pytest.mark.asyncio
async def test_create_is_idempotent_and_conflicting_payload_is_rejected(upload_api) -> None:
    client, factory = upload_api
    organization_id, project_id = await create_project(client)
    url = f"/api/v1/organizations/{organization_id}/projects/{project_id}/upload-sessions"
    request_headers = headers(key="m2-upload-idempotency-key")
    first = await client.post(url, headers=request_headers, json=payload())
    replay = await client.post(url, headers=request_headers, json=payload())
    conflict = await client.post(url, headers=request_headers, json=payload(size_bytes=2048))
    assert first.status_code == replay.status_code == 201
    assert first.json() == replay.json()
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert conflict.status_code == 409
    async with factory() as session:
        uploads = list(await session.scalars(select(UploadSessionModel)))
    assert len(uploads) == 1


@pytest.mark.parametrize(
    ("changes", "expected_status"),
    [
        ({"size_bytes": 0}, 422),
        ({"size_bytes": 20 * 1024**3 + 1}, 413),
        ({"sha256": "A" * 64}, 422),
        ({"sha256": "g" * 64}, 422),
        ({"display_name": "bad\nname"}, 422),
        ({"content_type": "bad\rtype"}, 422),
    ],
)
@pytest.mark.asyncio
async def test_input_boundaries_are_enforced(upload_api, changes, expected_status) -> None:
    client, _ = upload_api
    organization_id, project_id = await create_project(client)
    response = await client.post(
        f"/api/v1/organizations/{organization_id}/projects/{project_id}/upload-sessions",
        headers=headers(),
        json=payload(**changes),
    )
    assert response.status_code == expected_status


@pytest.mark.asyncio
async def test_archived_project_and_outsider_are_rejected_without_leak(upload_api) -> None:
    client, _ = upload_api
    organization_id, project_id = await create_project(client)
    outsider = await client.post(
        f"/api/v1/organizations/{organization_id}/projects/{project_id}/upload-sessions",
        headers=headers("outsider-token"),
        json=payload(),
    )
    project = await client.get(
        f"/api/v1/organizations/{organization_id}/projects/{project_id}", headers=headers()
    )
    await client.post(
        f"/api/v1/organizations/{organization_id}/projects/{project_id}:archive",
        headers={**headers(), "If-Match": project.headers["ETag"]},
    )
    archived = await client.post(
        f"/api/v1/organizations/{organization_id}/projects/{project_id}/upload-sessions",
        headers=headers(),
        json=payload(),
    )
    assert outsider.status_code == 404
    assert archived.status_code == 409
    assert archived.json()["code"] == "PROJECT_ARCHIVED"


@pytest.mark.asyncio
async def test_cancel_releases_reservation_and_replays(upload_api) -> None:
    client, factory = upload_api
    organization_id, project_id = await create_project(client)
    created = await client.post(
        f"/api/v1/organizations/{organization_id}/projects/{project_id}/upload-sessions",
        headers=headers(),
        json=payload(size_bytes=4096),
    )
    url = f"/api/v1/organizations/{organization_id}/projects/{project_id}/upload-sessions/{created.json()['id']}:cancel"
    request_headers = headers(key="m2-cancel-idempotency-key")
    cancelled = await client.post(url, headers=request_headers)
    replay = await client.post(url, headers=request_headers)
    assert cancelled.status_code == replay.status_code == 200
    assert cancelled.json()["status"] == "ABORTED"
    assert replay.headers["Idempotent-Replayed"] == "true"
    async with factory() as session:
        upload = await session.get(UploadSessionModel, uuid.UUID(created.json()["id"]))
    assert upload is not None and upload.reserved_bytes == 0


@pytest.mark.asyncio
async def test_get_lazily_expires_session_and_releases_reservation(upload_api) -> None:
    client, factory = upload_api
    organization_id, project_id = await create_project(client)
    created = await client.post(
        f"/api/v1/organizations/{organization_id}/projects/{project_id}/upload-sessions",
        headers=headers(),
        json=payload(),
    )
    upload_id = uuid.UUID(created.json()["id"])
    async with factory() as session:
        upload = await session.get(UploadSessionModel, upload_id)
        assert upload is not None
        upload.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    response = await client.get(
        f"/api/v1/organizations/{organization_id}/projects/{project_id}/upload-sessions/{upload_id}",
        headers=headers(),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "EXPIRED"
    async with factory() as session:
        upload = await session.get(UploadSessionModel, upload_id)
    assert upload is not None and upload.status is UploadSessionStatus.EXPIRED
    assert upload.reserved_bytes == 0
