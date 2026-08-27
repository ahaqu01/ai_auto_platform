from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from platform_api.auth.bff import BrowserSession, get_optional_bff_service
from platform_api.auth.dependencies import get_token_verifier
from platform_api.auth.identity import IdentityClaims
from platform_api.db.base import Base
from platform_api.db.session import get_session
from platform_api.main import create_app


class CookieBff:
    async def get_session(self, session_id: str):
        if session_id != "opaque-session":
            return None
        return BrowserSession(
            "opaque-session",
            "csrf-value",
            "access",
            "refresh",
            "id",
            9999999999,
            {
                "subject": "cookie-user",
                "email": "cookie@example.com",
                "display_name": "Cookie User",
            },
        )


class CookieVerifier:
    async def verify(self, token: str) -> IdentityClaims:
        assert token == "access"
        return IdentityClaims(
            "https://issuer.example/realms/platform",
            "cookie-user",
            "cookie@example.com",
            "Cookie User",
        )


@pytest.mark.asyncio
async def test_cookie_authenticates_api_and_write_requires_origin_csrf(
    tmp_path: Path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cookie.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_token_verifier] = lambda: CookieVerifier()
    app.dependency_overrides[get_optional_bff_service] = lambda: CookieBff()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        cookies={"platform_session": "opaque-session"},
    ) as client:
        listing = await client.get("/api/v1/organizations")
        denied = await client.post("/api/v1/organizations", json={"name": "Denied"})
        accepted = await client.post(
            "/api/v1/organizations",
            json={"name": "Accepted"},
            headers={"origin": "http://testserver", "x-csrf-token": "csrf-value"},
        )
    await engine.dispose()

    assert listing.status_code == 200
    assert denied.status_code == 403
    assert denied.json()["code"] == "CSRF_REJECTED"
    assert accepted.status_code == 201
