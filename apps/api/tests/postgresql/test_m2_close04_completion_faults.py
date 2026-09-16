import asyncio
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from test_m2_05_completion import FakeStorage, FakeTokenVerifier, headers, prepared

from platform_api.api.upload_sessions import get_object_storage
from platform_api.auth.dependencies import get_token_verifier
from platform_api.common.tenancy import set_tenant_context
from platform_api.db.models import ArtifactModel, UploadSessionModel, UserModel
from platform_api.db.session import get_session
from platform_api.main import create_app

pytestmark = [pytest.mark.asyncio, pytest.mark.postgresql]


async def tenant(session, base):
    actor = await session.scalar(select(UserModel.id).where(UserModel.external_subject == "owner"))
    await set_tenant_context(session, UUID(base.split("/")[4]), actor)


@pytest.fixture
async def fault_api(postgresql_database):
    faults = {"commit": False}

    class FaultSession(AsyncSession):
        async def commit(self):
            if faults["commit"] and any(
                isinstance(row, ArtifactModel) for row in self.identity_map.values()
            ):
                faults["commit"] = False
                raise RuntimeError("injected final database commit failure")
            await super().commit()

    factory = async_sessionmaker(
        postgresql_database.engine, class_=FaultSession, expire_on_commit=False
    )

    async def sessions():
        async with factory() as session:
            try:
                yield session
                if session.in_transaction():
                    await session.commit()
            except BaseException:
                await session.rollback()
                raise

    storage = FakeStorage(b"close04-postgresql")
    app = create_app()
    app.dependency_overrides[get_session] = sessions
    app.dependency_overrides[get_token_verifier] = FakeTokenVerifier
    app.dependency_overrides[get_object_storage] = lambda: storage
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        yield client, factory, storage, faults


async def test_concurrent_complete_publishes_one_artifact(fault_api):
    client, factory, storage, _ = fault_api
    base, body = await prepared(client, storage.content)
    responses = await asyncio.gather(
        client.post(f"{base}:complete", headers=headers(), json=body),
        client.post(f"{base}:complete", headers=headers(), json=body),
    )
    assert sorted(response.status_code for response in responses) == [200, 201]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    assert storage.completes == 1
    async with factory() as session:
        await tenant(session, base)
        assert await session.scalar(select(func.count()).select_from(ArtifactModel)) == 1


async def test_final_commit_failure_remains_completing_and_recovers(fault_api):
    client, factory, storage, faults = fault_api
    base, body = await prepared(client, storage.content)
    faults["commit"] = True
    failed = await client.post(f"{base}:complete", headers=headers(), json=body)
    assert failed.status_code == 500
    async with factory() as session:
        await tenant(session, base)
        assert await session.scalar(select(ArtifactModel)) is None
        upload = await session.scalar(select(UploadSessionModel))
        assert upload.status.value == "COMPLETING" and upload.reserved_bytes > 0
    recovered = await client.post(f"{base}:complete", headers=headers(), json=body)
    assert recovered.status_code == 201
    async with factory() as session:
        await tenant(session, base)
        assert await session.scalar(select(func.count()).select_from(ArtifactModel)) == 1
