import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from platform_api.auth.dependencies import get_token_verifier
from platform_api.auth.identity import IdentityClaims
from platform_api.common.errors import DomainError
from platform_api.db.base import Base
from platform_api.db.models import UserModel
from platform_api.db.session import get_session
from platform_api.main import create_app


@dataclass
class FakeTokenVerifier:
    async def verify(self, token: str) -> IdentityClaims:
        identities = {
            "owner-token": IdentityClaims(
                issuer="http://keycloak.test/realms/ai-platform",
                subject="owner-subject",
                email="owner@example.com",
                display_name="Owner",
            ),
            "outsider-token": IdentityClaims(
                issuer="http://keycloak.test/realms/ai-platform",
                subject="outsider-subject",
                email="outsider@example.com",
                display_name="Outsider",
            ),
        }
        try:
            return identities[token]
        except KeyError as exc:
            raise DomainError("AUTHENTICATION_REQUIRED", "身份凭证无效", 401) from exc


@pytest.fixture
async def authenticated_api(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'auth-test.db'}")
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
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, factory
    await engine.dispose()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": uuid.uuid4().hex}


@pytest.mark.asyncio
async def test_protected_api_rejects_missing_and_invalid_token(
    authenticated_api,
) -> None:
    client, _ = authenticated_api
    missing = await client.get("/api/v1/organizations")
    invalid = await client.get("/api/v1/organizations", headers=bearer("invalid-token"))
    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert invalid.json()["code"] == "AUTHENTICATION_REQUIRED"
    assert invalid.json()["traceId"]


@pytest.mark.asyncio
async def test_current_identity_is_synced_once_and_owns_new_organization(
    authenticated_api,
) -> None:
    client, factory = authenticated_api
    payload = {"name": "雩江科技"}
    first = await client.post(
        "/api/v1/organizations", headers=bearer("owner-token"), json=payload
    )
    second_list = await client.get(
        "/api/v1/organizations", headers=bearer("owner-token")
    )
    assert first.status_code == 201
    assert [item["id"] for item in second_list.json()] == [first.json()["id"]]

    async with factory() as session:
        user_count = await session.scalar(select(func.count()).select_from(UserModel))
        user = await session.scalar(select(UserModel))
    assert user_count == 1
    assert user is not None
    assert user.external_issuer == "http://keycloak.test/realms/ai-platform"
    assert user.external_subject == "owner-subject"


@pytest.mark.asyncio
async def test_non_member_cannot_use_known_organization_id(authenticated_api) -> None:
    client, _ = authenticated_api
    organization = await client.post(
        "/api/v1/organizations",
        headers=bearer("owner-token"),
        json={"name": "隔离测试企业"},
    )
    organization_id = organization.json()["id"]
    denied = await client.get(
        f"/api/v1/organizations/{organization_id}/projects",
        headers=bearer("outsider-token"),
    )
    assert denied.status_code == 404
    assert denied.json()["code"] == "ORGANIZATION_NOT_FOUND"


@pytest.mark.asyncio
async def test_user_id_query_parameter_is_not_in_openapi_contract(
    authenticated_api,
) -> None:
    client, _ = authenticated_api
    response = await client.get("/openapi.json")
    document = response.json()
    for path, operations in document["paths"].items():
        if not path.startswith("/api/v1/"):
            continue
        for operation in operations.values():
            parameter_names = {item["name"] for item in operation.get("parameters", [])}
            assert "user_id" not in parameter_names
