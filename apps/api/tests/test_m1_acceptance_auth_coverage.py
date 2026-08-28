from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

import platform_api.auth.bff as bff_module
from platform_api.auth import dependencies
from platform_api.auth.bff import (
    BrowserSession,
    get_bff_service,
    get_optional_bff_service,
)
from platform_api.common import tenancy
from platform_api.common.errors import DomainError
from platform_api.main import create_app
from platform_api.settings import Settings


class SessionService:
    def __init__(self, session):
        self.session = session

    async def get_session(self, _session_id):
        return self.session

    async def logout(self, _session_id):
        return None


def browser_session():
    return BrowserSession(
        "session",
        "csrf",
        "access",
        "refresh",
        "id",
        9999999999,
        {"subject": "subject"},
    )


def test_browser_session_and_logout_missing_or_expired_cookie_branches() -> None:
    app = create_app()
    service = SessionService(None)
    app.dependency_overrides[bff_module.get_bff_service] = lambda: service
    api = TestClient(app)
    assert api.get("/auth/session").json() == {"authenticated": False}
    api.cookies.set("platform_session", "expired")
    assert api.get("/auth/session").json() == {"authenticated": False}
    assert api.post("/auth/logout").status_code == 401

    api.cookies.clear()
    assert api.post("/auth/logout").status_code == 401
    service.session = browser_session()
    api.cookies.set("platform_session", "session")
    assert (
        api.post(
            "/auth/logout",
            headers={"origin": "http://testserver", "x-csrf-token": "csrf"},
        ).status_code
        == 204
    )


def test_optional_bff_service_configuration_branches(monkeypatch) -> None:
    monkeypatch.setattr(bff_module, "_service", None)
    monkeypatch.setattr(
        bff_module,
        "get_settings",
        lambda: Settings(redis_url=None, keycloak_issuer=None, _env_file=None),
    )
    assert get_optional_bff_service() is None
    with pytest.raises(DomainError) as unavailable:
        get_bff_service()
    assert unavailable.value.code == "AUTHENTICATION_UNAVAILABLE"

    configured = Settings(
        redis_url="redis://localhost:6379/0",
        keycloak_issuer="https://issuer.example/realms/platform",
        bff_client_secret="secret",
        _env_file=None,
    )
    monkeypatch.setattr(bff_module, "get_settings", lambda: configured)
    monkeypatch.setattr(
        bff_module.Redis, "from_url", lambda *_args, **_kwargs: SimpleNamespace()
    )
    monkeypatch.setattr(dependencies, "get_token_verifier", lambda: SimpleNamespace())
    monkeypatch.setattr(
        dependencies, "get_bff_id_token_verifier", lambda: SimpleNamespace()
    )
    service = get_optional_bff_service()
    assert service is get_optional_bff_service()
    monkeypatch.setattr(bff_module, "_service", None)


class FakeAsyncClient:
    def __init__(self, response=None, error=None, **_kwargs):
        self.response = response
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, _url, data):
        assert data["client_id"] and data["client_secret"]
        if self.error:
            raise self.error
        return self.response


@pytest.mark.asyncio
async def test_bff_http_post_success_and_failure(monkeypatch) -> None:
    settings = Settings(
        keycloak_issuer="https://issuer.example/realms/platform",
        bff_client_secret="secret",
        _env_file=None,
    )
    service = bff_module.BffService(
        settings, SimpleNamespace(), SimpleNamespace(), SimpleNamespace()
    )
    response = SimpleNamespace(raise_for_status=lambda: None)
    monkeypatch.setattr(
        bff_module.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(response=response, **kwargs),
    )
    assert await service._post("https://issuer.example/token", {}) is response
    monkeypatch.setattr(
        bff_module.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(error=httpx.ConnectError("down"), **kwargs),
    )
    with pytest.raises(DomainError) as error:
        await service._post("https://issuer.example/token", {})
    assert error.value.code == "IDENTITY_PROVIDER_UNAVAILABLE"


def test_oidc_verifier_configuration_matrix(monkeypatch) -> None:
    missing = Settings(keycloak_issuer=None, _env_file=None)
    monkeypatch.setattr(dependencies, "get_settings", lambda: missing)
    assert (
        type(dependencies._oidc_verifier(None)).__name__ == "UnavailableTokenVerifier"
    )

    internal = Settings(
        app_env="local",
        keycloak_issuer="https://public.example/realms/platform",
        keycloak_internal_issuer="http://keycloak:8080/realms/platform",
        _env_file=None,
    )
    monkeypatch.setattr(dependencies, "get_settings", lambda: internal)
    monkeypatch.setattr(
        dependencies.jwt, "PyJWKClient", lambda *_args, **_kwargs: "jwks"
    )
    assert dependencies._oidc_verifier("api").jwks_client == "jwks"

    external = Settings(
        app_env="local",
        keycloak_issuer="https://public.example/realms/platform",
        _env_file=None,
    )
    monkeypatch.setattr(dependencies, "get_settings", lambda: external)
    assert dependencies._oidc_verifier("api").audience == "api"


class FakeTenantSession:
    def __init__(self, dialect, scalar_values=()):
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect))
        self.scalar_values = list(scalar_values)
        self.executed = []

    def get_bind(self):
        return self.bind

    async def execute(self, statement):
        self.executed.append(statement)

    async def scalar(self, _statement):
        return self.scalar_values.pop(0)


@pytest.mark.asyncio
async def test_tenant_context_sqlite_postgresql_and_invite_resolution(
    monkeypatch,
) -> None:
    actor_id, organization_id = uuid4(), uuid4()
    sqlite = FakeTenantSession("sqlite", [organization_id])
    await tenancy.activate_actor_context(sqlite, actor_id)
    await tenancy.set_tenant_context(sqlite, organization_id, actor_id)
    assert sqlite.executed == []
    assert (
        await tenancy.resolve_invite_tenant(sqlite, b"hash", actor_id)
        == organization_id
    )

    postgresql = FakeTenantSession("postgresql", [organization_id])
    assert (
        await tenancy.resolve_invite_tenant(postgresql, b"hash", actor_id)
        == organization_id
    )
    assert len(postgresql.executed) == 3

    with pytest.raises(DomainError) as missing:
        await tenancy.resolve_invite_tenant(
            FakeTenantSession("sqlite", [None]), b"x", actor_id
        )
    assert missing.value.code == "INVITE_NOT_FOUND"
