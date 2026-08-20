from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from platform_api.db.base import Base
from platform_api.db.models import UserModel
from platform_api.db.session import get_session
from platform_api.main import create_app


@pytest.fixture
async def api(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, factory
    await engine.dispose()


async def owner_id(factory: async_sessionmaker[AsyncSession], email: str) -> str:
    async with factory() as session:
        user = await session.scalar(select(UserModel).where(UserModel.email == email))
        assert user is not None
        return str(user.id)


@pytest.mark.asyncio
async def test_organization_and_project_are_tenant_scoped(api) -> None:
    client, factory = api
    created_org = await client.post(
        "/api/v1/organizations",
        json={
            "name": "雩江科技",
            "owner_email": "owner@example.com",
            "owner_display_name": "Owner",
        },
    )
    assert created_org.status_code == 201
    organization_id = created_org.json()["id"]
    real_owner_id = await owner_id(factory, "owner@example.com")

    organizations = await client.get(
        "/api/v1/organizations", params={"user_id": real_owner_id}
    )
    assert [item["id"] for item in organizations.json()] == [organization_id]

    denied = await client.post(
        f"/api/v1/organizations/{organization_id}/projects",
        params={"user_id": "00000000-0000-0000-0000-000000000001"},
        json={"code": "vision-demo", "name": "视觉演示"},
    )
    assert denied.status_code == 404
    assert denied.json()["code"] == "ORGANIZATION_NOT_FOUND"


@pytest.mark.asyncio
async def test_duplicate_project_code_returns_conflict(api) -> None:
    client, factory = api
    created_org = await client.post(
        "/api/v1/organizations",
        json={
            "name": "测试企业",
            "owner_email": "admin@example.com",
            "owner_display_name": "Admin",
        },
    )
    organization_id = created_org.json()["id"]
    user_id = await owner_id(factory, "admin@example.com")
    url = f"/api/v1/organizations/{organization_id}/projects"
    payload = {"code": "vision-demo", "name": "视觉演示"}
    first = await client.post(url, params={"user_id": user_id}, json=payload)
    duplicate = await client.post(url, params={"user_id": user_id}, json=payload)
    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "PROJECT_CODE_EXISTS"

    projects = await client.get(url, params={"user_id": user_id})
    assert len(projects.json()) == 1
