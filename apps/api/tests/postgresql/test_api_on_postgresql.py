import uuid

import pytest
from sqlalchemy import func, select, text

from platform_api.db.models import (
    OrganizationMemberModel,
    ProjectModel,
    UserModel,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.postgresql]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": uuid.uuid4().hex}


async def test_authenticated_tenant_lifecycle_runs_through_postgresql(
    postgresql_api,
) -> None:
    client = postgresql_api.client
    async with postgresql_api.database.engine.connect() as connection:
        assert connection.dialect.name == "postgresql"
        assert await connection.scalar(text("select current_schema()")) == (
            postgresql_api.database.schema
        )

    created_organization = await client.post(
        "/api/v1/organizations",
        headers=bearer("owner-token"),
        json={"name": "PostgreSQL 验收企业"},
    )
    assert created_organization.status_code == 201
    organization_id = created_organization.json()["id"]

    organizations = await client.get(
        "/api/v1/organizations", headers=bearer("owner-token")
    )
    assert [item["id"] for item in organizations.json()] == [organization_id]

    created_project = await client.post(
        f"/api/v1/organizations/{organization_id}/projects",
        headers=bearer("owner-token"),
        json={"code": "pg-lifecycle", "name": "PostgreSQL 生命周期"},
    )
    assert created_project.status_code == 201

    projects = await client.get(
        f"/api/v1/organizations/{organization_id}/projects",
        headers=bearer("owner-token"),
    )
    assert projects.status_code == 200
    assert [item["id"] for item in projects.json()] == [created_project.json()["id"]]

    async with postgresql_api.database.session_factory() as session:
        user_count = await session.scalar(select(func.count()).select_from(UserModel))
        membership_count = await session.scalar(
            select(func.count()).select_from(OrganizationMemberModel)
        )
        project = await session.scalar(select(ProjectModel))
    assert user_count == 1
    assert membership_count == 1
    assert project is not None
    assert project.code == "pg-lifecycle"


async def test_non_member_is_hidden_on_postgresql(postgresql_api) -> None:
    client = postgresql_api.client
    organization = await client.post(
        "/api/v1/organizations",
        headers=bearer("owner-token"),
        json={"name": "PostgreSQL 隔离企业"},
    )
    organization_id = organization.json()["id"]

    denied = await client.get(
        f"/api/v1/organizations/{organization_id}/projects",
        headers=bearer("outsider-token"),
    )
    assert denied.status_code == 404
    assert denied.json()["code"] == "ORGANIZATION_NOT_FOUND"


async def test_failed_project_request_rolls_back_and_session_remains_usable(
    postgresql_api,
) -> None:
    client = postgresql_api.client
    organization = await client.post(
        "/api/v1/organizations",
        headers=bearer("owner-token"),
        json={"name": "PostgreSQL 回滚企业"},
    )
    organization_id = organization.json()["id"]
    endpoint = f"/api/v1/organizations/{organization_id}/projects"
    payload = {"code": "duplicate", "name": "第一次成功"}

    first = await client.post(endpoint, headers=bearer("owner-token"), json=payload)
    duplicate = await client.post(
        endpoint,
        headers=bearer("owner-token"),
        json={"code": "duplicate", "name": "第二次冲突"},
    )
    after_failure = await client.get(endpoint, headers=bearer("owner-token"))

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "PROJECT_CODE_EXISTS"
    assert after_failure.status_code == 200
    assert [item["id"] for item in after_failure.json()] == [first.json()["id"]]

    async with postgresql_api.database.session_factory() as session:
        project_count = await session.scalar(
            select(func.count()).select_from(ProjectModel)
        )
    assert project_count == 1
