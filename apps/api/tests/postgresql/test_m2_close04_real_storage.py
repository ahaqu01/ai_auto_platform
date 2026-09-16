import hashlib
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from test_m2_05_completion import FakeTokenVerifier, headers

from platform_api.api.upload_sessions import get_object_storage
from platform_api.auth.dependencies import get_token_verifier
from platform_api.common.tenancy import set_tenant_context
from platform_api.db.models import ArtifactModel
from platform_api.db.session import get_session
from platform_api.main import create_app
from platform_api.modules.artifact.domain import ArtifactStatus
from platform_api.modules.artifact.maintenance import ArtifactMaintenanceService
from platform_api.modules.artifact.storage import ObjectStorageError, StorageErrorCode
from platform_api.modules.artifact.storage_runtime import build_object_storage
from platform_api.settings import get_settings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.postgresql,
    pytest.mark.skipif(
        os.environ.get("M2_REAL_STORAGE_CONFIRM") != "ISOLATED_DATABASE_REAL_OSS",
        reason="explicit isolated database and real OSS confirmation required",
    ),
]


async def test_real_oss_postgresql_authorization_states_and_reconcile(postgresql_database):
    storage = build_object_storage(get_settings())
    assert storage is not None
    factory = postgresql_database.session_factory

    async def sessions():
        async with factory() as session:
            try:
                yield session
                if session.in_transaction():
                    await session.commit()
            except BaseException:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_session] = sessions
    app.dependency_overrides[get_token_verifier] = FakeTokenVerifier
    app.dependency_overrides[get_object_storage] = lambda: storage
    keys = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        org = await client.post("/api/v1/organizations", headers=headers(), json={"name": "Close04 Real OSS"})
        assert org.status_code == 201
        organization_id = UUID(org.json()["id"])
        project = await client.post(
            f"/api/v1/organizations/{organization_id}/projects", headers=headers(),
            json={"code": uuid4().hex[:12], "name": "Real matrix"},
        )
        assert project.status_code == 201
        project_id = UUID(project.json()["id"])
        project_url = f"/api/v1/organizations/{organization_id}/projects/{project_id}"
        content = b"M2-CLOSE-04 real OSS and PostgreSQL"
        created = await client.post(
            f"{project_url}/upload-sessions", headers=headers(),
            json={"display_name": "close04.bin", "size_bytes": len(content),
                  "sha256": hashlib.sha256(content).hexdigest(), "content_type": "application/octet-stream"},
        )
        assert created.status_code == 201
        base = f"{project_url}/upload-sessions/{created.json()['id']}"
        actor_id = UUID(created.json()["created_by"])
        signed = await client.post(f"{base}/parts:sign", headers=headers(), json={"part_numbers": [1]})
        assert signed.status_code == 200
        async with factory() as db:
            await set_tenant_context(db, organization_id, actor_id)
            from platform_api.db.models import UploadSessionModel
            upload = await db.get(UploadSessionModel, UUID(created.json()["id"]))
            keys.append(upload.object_key)
        try:
            async with httpx.AsyncClient(timeout=30) as network:
                put = await network.put(signed.json()[0]["url"], content=content)
                assert put.status_code == 200
                etag = put.headers["etag"]
            registered = await client.put(f"{base}/parts/1", headers=headers(), json={"etag": etag, "size_bytes": len(content)})
            replay = await client.put(f"{base}/parts/1", headers=headers(), json={"etag": etag, "size_bytes": len(content)})
            assert registered.status_code == replay.status_code == 200
            completed = await client.post(f"{base}:complete", headers=headers(), json={"parts": [{"part_number": 1, "etag": etag}]})
            assert completed.status_code == 201
            artifact_id = UUID(completed.json()["id"])
            artifact_url = f"{project_url}/artifacts/{artifact_id}"
            download = await client.post(f"{artifact_url}:download-url", headers=headers(), json={})
            assert download.status_code == 200
            async with httpx.AsyncClient(timeout=30) as network:
                received = await network.get(download.json()["url"])
                assert received.status_code == 200 and received.content == content

            denied_headers = {"Authorization": "Bearer outsider-token", "Idempotency-Key": uuid4().hex}
            # FakeTokenVerifier intentionally accepts only the owner; replace it
            # with the existing multi-identity verifier for the non-member check.
            from .conftest import FakeTokenVerifier as MultiTokenVerifier
            app.dependency_overrides[get_token_verifier] = MultiTokenVerifier
            denied = await client.get(artifact_url, headers=denied_headers)
            assert denied.status_code == 404
            app.dependency_overrides[get_token_verifier] = FakeTokenVerifier
            unauthenticated = await client.get(artifact_url)
            assert unauthenticated.status_code == 401

            project_read = await client.get(project_url, headers=headers())
            archived = await client.post(f"{project_url}:archive", headers={**headers(), "If-Match": project_read.headers["etag"]})
            assert archived.status_code == 200
            assert (await client.get(artifact_url, headers=headers())).status_code == 200
            blocked_delete = await client.delete(artifact_url, headers={**headers(), "If-Match": '"1"'})
            assert blocked_delete.status_code == 409

            for state in (
                ArtifactStatus.QUARANTINED,
                ArtifactStatus.DELETING,
                ArtifactStatus.DELETED,
            ):
                async with factory() as db:
                    await set_tenant_context(db, organization_id, actor_id)
                    artifact = await db.get(ArtifactModel, artifact_id)
                    artifact.status = state
                    await db.commit()
                response = await client.post(f"{artifact_url}:download-url", headers=headers(), json={})
                assert response.status_code == 409
                detail = await client.get(artifact_url, headers=headers())
                assert detail.status_code == (
                    404
                    if state in {ArtifactStatus.DELETING, ArtifactStatus.DELETED}
                    else 200
                )

            @asynccontextmanager
            async def tenant_sessions():
                async with factory() as db:
                    await set_tenant_context(db, organization_id, actor_id)
                    yield db

            class ScopedStorage:
                fail_delete = True
                async def delete(self, key):
                    assert key in keys
                    if self.fail_delete:
                        raise ObjectStorageError(StorageErrorCode.TIMEOUT, "injected", retryable=True)
                    await storage.delete(key)
                async def head(self, key):
                    assert key in keys
                    return await storage.head(key)
                async def list_objects(self, prefix):
                    if False:
                        yield None

            async with tenant_sessions() as db:
                artifact = await db.get(ArtifactModel, artifact_id)
                artifact.status = ArtifactStatus.DELETING
                await db.commit()
            scoped = ScopedStorage()
            now = datetime.now(UTC)
            first = await ArtifactMaintenanceService(tenant_sessions, scoped, now=lambda: now).run_once()
            assert first.failures == 1 and first.artifacts_deleted == 0
            immediate = await ArtifactMaintenanceService(tenant_sessions, scoped, now=lambda: now).run_once()
            assert immediate.failures == 0 and immediate.artifacts_deleted == 0
            scoped.fail_delete = False
            recovered = await ArtifactMaintenanceService(tenant_sessions, scoped, now=lambda: now + timedelta(seconds=31)).run_once()
            repeated = await ArtifactMaintenanceService(tenant_sessions, scoped, now=lambda: now + timedelta(seconds=32)).run_once()
            assert recovered.artifacts_deleted == 1 and repeated.artifacts_deleted == 0
            print("real_oss_postgresql_matrix PASS available/download/nonmember/noauth/archived/quarantined/deleting/deleted/delete-backoff/idempotency")
        finally:
            for key in keys:
                try:
                    await storage.delete(key)
                except ObjectStorageError as exc:
                    if exc.code is not StorageErrorCode.NOT_FOUND:
                        raise
