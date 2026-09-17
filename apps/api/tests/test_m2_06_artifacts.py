import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
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
from platform_api.db.models import ArtifactModel, UploadSessionModel, UserModel
from platform_api.db.session import get_session
from platform_api.main import create_app
from platform_api.modules.artifact.domain import (
    ArtifactStatus,
    IntegrityStatus,
    SecurityScanStatus,
    UploadSessionStatus,
)
from platform_api.modules.artifact.storage import PresignedRequest


class FakeTokenVerifier:
    async def verify(self, token: str) -> IdentityClaims:
        identities = {
            "owner-token": IdentityClaims(
                "https://issuer.test", "owner", "owner@example.com", "Owner"
            ),
            "outsider-token": IdentityClaims(
                "https://issuer.test", "outsider", "out@example.com", "Outsider"
            ),
        }
        try:
            return identities[token]
        except KeyError as exc:
            raise DomainError("AUTHENTICATION_REQUIRED", "invalid", 401) from exc


@dataclass
class FakeStorage:
    downloads: list[tuple[str, int, str]] = field(default_factory=list)

    async def sign_download(
        self, object_key, expires_in_seconds, download_name, *, cancellation=None
    ):
        self.downloads.append((object_key, expires_in_seconds, download_name))
        return PresignedRequest(
            "https://storage.test/object?signature=secret", expires_in_seconds
        )


@pytest.fixture
async def artifact_api(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'artifacts.db'}")
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
        yield client, factory, storage
    await engine.dispose()


def headers(token="owner-token", key=None):
    return {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": key or uuid.uuid4().hex,
    }


async def seed(
    client: AsyncClient,
    factory,
    *,
    status=ArtifactStatus.AVAILABLE,
    name='report "final".zip',
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
    async with factory() as session:
        owner = await session.scalar(
            select(UserModel).where(UserModel.external_subject == "owner")
        )
        upload = UploadSessionModel(
            organization_id=uuid.UUID(org_id),
            project_id=uuid.UUID(project_id),
            created_by=owner.id,
            display_name=name,
            object_key=f"v1/o/{uuid.uuid4().hex}",
            expected_size=10,
            expected_sha256=hashlib.sha256(b"0123456789").hexdigest(),
            declared_content_type="application/zip",
            status=UploadSessionStatus.COMPLETED,
            reserved_bytes=0,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            completed_at=datetime.now(UTC),
        )
        session.add(upload)
        await session.flush()
        artifact = ArtifactModel(
            upload_session_id=upload.id,
            organization_id=uuid.UUID(org_id),
            project_id=uuid.UUID(project_id),
            created_by=owner.id,
            display_name=name,
            object_key=upload.object_key,
            bucket_alias="primary",
            size_bytes=10,
            expected_sha256=upload.expected_sha256,
            verified_sha256=upload.expected_sha256,
            declared_content_type="application/zip",
            detected_content_type="application/zip",
            integrity_status=IntegrityStatus.VERIFIED,
            security_scan_status=SecurityScanStatus.NOT_REQUIRED,
            status=status,
        )
        session.add(artifact)
        await session.commit()
        artifact_id = str(artifact.id)
    base = f"/api/v1/organizations/{org_id}/projects/{project_id}/artifacts"
    return base, artifact_id, project_id


@pytest.mark.asyncio
async def test_list_detail_cursor_and_no_storage_identifiers(artifact_api):
    client, factory, _ = artifact_api
    base, artifact_id, _ = await seed(client, factory)
    page = await client.get(base, headers=headers(), params={"limit": 1})
    detail = await client.get(f"{base}/{artifact_id}", headers=headers())
    assert page.status_code == detail.status_code == 200
    assert page.json()["items"][0]["id"] == artifact_id
    assert "object_key" not in detail.json() and "bucket_alias" not in detail.json()
    assert detail.headers["ETag"] == '"1"'


@pytest.mark.asyncio
async def test_download_available_uses_short_ttl_and_safe_filename(artifact_api):
    client, factory, storage = artifact_api
    base, artifact_id, _ = await seed(client, factory)
    response = await client.post(
        f"{base}/{artifact_id}:download-url",
        headers=headers(),
        json={"expires_in_seconds": 600},
    )
    assert response.status_code == 200
    assert response.json()["expires_in_seconds"] == 600
    assert response.json()["content_disposition"].startswith(
        "attachment; filename*=UTF-8''"
    )
    assert storage.downloads[0][2] == "report _final_.zip"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ttl,expected", [(59, 422), (60, 200), (900, 200), (901, 422), (3600, 422)]
)
async def test_download_ttl_contract(artifact_api, ttl, expected):
    client, factory, storage = artifact_api
    base, artifact_id, _ = await seed(client, factory)
    response = await client.post(
        f"{base}/{artifact_id}:download-url",
        headers=headers(),
        json={"expires_in_seconds": ttl},
    )
    assert response.status_code == expected
    assert len(storage.downloads) == (1 if expected == 200 else 0)


@pytest.mark.asyncio
async def test_quarantined_and_outsider_cannot_download(artifact_api):
    client, factory, storage = artifact_api
    base, artifact_id, _ = await seed(
        client, factory, status=ArtifactStatus.QUARANTINED
    )
    unavailable = await client.post(
        f"{base}/{artifact_id}:download-url", headers=headers(), json={}
    )
    outsider = await client.get(
        f"{base}/{artifact_id}", headers=headers("outsider-token")
    )
    assert (
        unavailable.status_code == 409
        and unavailable.json()["code"] == "ARTIFACT_NOT_AVAILABLE"
    )
    assert outsider.status_code == 404 and storage.downloads == []


@pytest.mark.asyncio
async def test_delete_is_versioned_idempotent_and_hidden(artifact_api):
    client, factory, _ = artifact_api
    base, artifact_id, _ = await seed(client, factory)
    request_headers = {**headers(key="artifact-delete-key"), "If-Match": '"1"'}
    deleted = await client.delete(f"{base}/{artifact_id}", headers=request_headers)
    replay = await client.delete(f"{base}/{artifact_id}", headers=request_headers)
    hidden = await client.get(f"{base}/{artifact_id}", headers=headers())
    listing = await client.get(base, headers=headers())
    assert deleted.status_code == replay.status_code == 200
    assert (
        deleted.json()["status"] == "DELETING"
        and replay.headers["Idempotent-Replayed"] == "true"
    )
    assert hidden.status_code == 404 and listing.json()["items"] == []


@pytest.mark.asyncio
async def test_archived_project_rejects_delete_but_allows_read(artifact_api):
    client, factory, _ = artifact_api
    base, artifact_id, _ = await seed(client, factory)
    project_url = base.removesuffix("/artifacts")
    project = await client.get(project_url, headers=headers())
    await client.post(
        f"{project_url}:archive",
        headers={**headers(), "If-Match": project.headers["ETag"]},
    )
    read = await client.get(f"{base}/{artifact_id}", headers=headers())
    delete = await client.delete(
        f"{base}/{artifact_id}", headers={**headers(), "If-Match": '"1"'}
    )
    assert read.status_code == 200
    assert delete.status_code == 409 and delete.json()["code"] == "PROJECT_ARCHIVED"
