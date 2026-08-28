import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from platform_api.api.organization_access import (
    _ensure_other_owner,
    _lock_and_authorize,
    _target,
    change_member_role,
    remove_organization_member,
    require_organization_admin,
    require_organization_member,
)
from platform_api.api.projects import (
    _check_version,
    _commit_project,
    _decode_cursor,
    _encode_cursor,
    _expected_version,
    _require_project_admin,
    _visible_project,
)
from platform_api.auth.bff import (
    BffService,
    BrowserSession,
    MemorySessionStore,
    RedisSessionStore,
)
from platform_api.auth.identity import IdentityClaims
from platform_api.common.errors import DomainError
from platform_api.modules.organization.domain import OrganizationRole
from platform_api.modules.project.domain import ProjectRole
from platform_api.settings import Settings


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, key, value, **_kwargs):
        self.values[key] = value

    async def get(self, key):
        return self.values.get(key)

    async def getdel(self, key):
        return self.values.pop(key, None)

    async def delete(self, key):
        self.values.pop(key, None)


class AcceptingVerifier:
    async def verify(self, token: str) -> IdentityClaims:
        if token == "invalid":
            raise DomainError("AUTHENTICATION_REQUIRED", "invalid", 401)
        return IdentityClaims("issuer", "subject", "user@example.com", "User")


def bff_service(store=None) -> BffService:
    return BffService(
        Settings(
            keycloak_issuer="https://issuer.example/realms/platform",
            bff_client_secret="secret",
            _env_file=None,
        ),
        store or MemorySessionStore(),
        AcceptingVerifier(),
        AcceptingVerifier(),
    )


@pytest.mark.asyncio
async def test_redis_session_store_round_trip_and_missing_values() -> None:
    redis = FakeRedis()
    store = RedisSessionStore(redis, session_ttl=600)
    state = await store.create_login("/console", "verifier", "nonce")
    assert (await store.consume_login(state)).return_to == "/console"
    assert await store.consume_login(state) is None

    session = await store.create_session(
        access_token="access",
        refresh_token="refresh",
        id_token="id",
        expires_in=300,
        identity={"subject": "subject"},
    )
    assert await store.get_session(session.session_id) == session
    await store.delete_session(session.session_id)
    assert await store.get_session(session.session_id) is None


@pytest.mark.asyncio
async def test_bff_refresh_success_failure_and_logout_are_fail_closed() -> None:
    store = MemorySessionStore()
    service = bff_service(store)
    active = await store.create_session(
        access_token="access",
        refresh_token="refresh",
        id_token="id",
        expires_in=300,
        identity={"subject": "subject"},
    )
    assert await service.get_session(active.session_id) == active
    assert await service.get_session("missing") is None

    expired = BrowserSession(
        "expired", "csrf", "old", "refresh", "id", int(time.time()), {}
    )
    await store.save_session(expired)
    service._token_request = AsyncMock(
        return_value={"access_token": "new", "expires_in": 120}
    )
    refreshed = await service.get_session("expired")
    assert refreshed.access_token == "new"
    assert refreshed.refresh_token == "refresh"

    broken = BrowserSession(
        "broken", "csrf", "old", "refresh", "id", int(time.time()), {}
    )
    await store.save_session(broken)
    service._token_request = AsyncMock(return_value={})
    assert await service.get_session("broken") is None
    assert await store.get_session("broken") is None

    service._post = AsyncMock(side_effect=DomainError("IDP", "down", 502))
    await service.logout("expired")
    assert await store.get_session("expired") is None
    await service.logout("missing")


@pytest.mark.asyncio
async def test_bff_token_response_must_be_json() -> None:
    service = bff_service()
    response = SimpleNamespace(json=lambda: (_ for _ in ()).throw(ValueError()))
    service._post = AsyncMock(return_value=response)
    with pytest.raises(DomainError) as error:
        await service._token_request({"grant_type": "refresh_token"})
    assert error.value.code == "IDENTITY_PROVIDER_ERROR"


class FakeSession:
    def __init__(self, *, scalar_values=(), get_values=()) -> None:
        self.scalar_values = list(scalar_values)
        self.get_values = list(get_values)
        self.deleted = []
        self.commits = 0
        self.rollbacks = 0
        self.refreshed = []

    async def scalar(self, _statement):
        return self.scalar_values.pop(0)

    async def get(self, _model, _key):
        return self.get_values.pop(0)

    async def delete(self, value):
        self.deleted.append(value)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, value):
        self.refreshed.append(value)


@pytest.mark.asyncio
async def test_organization_access_denials_and_last_owner_guards(monkeypatch) -> None:
    monkeypatch.setattr(
        "platform_api.api.organization_access.set_tenant_context", AsyncMock()
    )
    organization_id = uuid4()
    actor_id = uuid4()

    with pytest.raises(DomainError, match="企业不存在"):
        await require_organization_member(
            FakeSession(scalar_values=[None]), organization_id, actor_id
        )
    member = SimpleNamespace(role=OrganizationRole.MEMBER)
    with pytest.raises(DomainError, match="管理员"):
        await require_organization_admin(
            FakeSession(scalar_values=[member]), organization_id, actor_id
        )
    with pytest.raises(DomainError, match="企业不存在"):
        await _lock_and_authorize(
            FakeSession(scalar_values=[None]), organization_id, actor_id
        )
    with pytest.raises(DomainError, match="成员不存在"):
        await _target(FakeSession(scalar_values=[None]), organization_id, actor_id)
    with pytest.raises(DomainError, match="至少保留"):
        await _ensure_other_owner(FakeSession(scalar_values=[1]), organization_id)
    await _ensure_other_owner(FakeSession(scalar_values=[2]), organization_id)


@pytest.mark.asyncio
async def test_owner_role_changes_and_removal_permissions(monkeypatch) -> None:
    organization_id, actor_id, member_id = uuid4(), uuid4(), uuid4()
    admin = SimpleNamespace(role=OrganizationRole.ADMIN)
    owner = SimpleNamespace(role=OrganizationRole.OWNER)
    member = SimpleNamespace(role=OrganizationRole.MEMBER)
    monkeypatch.setattr(
        "platform_api.api.organization_access._lock_and_authorize",
        AsyncMock(return_value=admin),
    )
    monkeypatch.setattr(
        "platform_api.api.organization_access._target", AsyncMock(return_value=owner)
    )
    with pytest.raises(DomainError, match="所有者权限"):
        await change_member_role(
            FakeSession(), organization_id, actor_id, member_id, OrganizationRole.MEMBER
        )
    with pytest.raises(DomainError, match="所有者权限"):
        await remove_organization_member(
            FakeSession(), organization_id, actor_id, member_id
        )

    monkeypatch.setattr(
        "platform_api.api.organization_access._lock_and_authorize",
        AsyncMock(return_value=owner),
    )
    monkeypatch.setattr(
        "platform_api.api.organization_access._target", AsyncMock(return_value=member)
    )
    session = FakeSession()
    changed = await change_member_role(
        session, organization_id, actor_id, member_id, OrganizationRole.ADMIN
    )
    assert changed.role is OrganizationRole.ADMIN
    removed = await remove_organization_member(
        session, organization_id, actor_id, member_id
    )
    assert removed is member and session.deleted == [member]


def test_project_version_and_cursor_validation() -> None:
    project = SimpleNamespace(
        created_at=SimpleNamespace(isoformat=lambda: "2026-01-01T00:00:00+00:00"),
        id=uuid4(),
        version=3,
    )
    cursor = _encode_cursor(project)
    assert _decode_cursor(cursor)[1] == project.id
    with pytest.raises(DomainError, match="游标"):
        _decode_cursor("not-json")
    with pytest.raises(DomainError, match="必须提供"):
        _expected_version(None)
    with pytest.raises(DomainError, match="带引号"):
        _expected_version("3")
    with pytest.raises(DomainError, match="带引号"):
        _expected_version('"bad"')
    assert _expected_version('W/"3"') == 3
    with pytest.raises(DomainError, match="版本已变化"):
        _check_version(project, '"2"')
    _check_version(project, '"3"')


@pytest.mark.asyncio
async def test_project_visibility_and_admin_matrix(monkeypatch) -> None:
    organization_id, project_id, actor_id = uuid4(), uuid4(), uuid4()
    member = SimpleNamespace(role=OrganizationRole.MEMBER)
    project = SimpleNamespace(id=project_id)
    monkeypatch.setattr(
        "platform_api.api.projects.require_organization_member",
        AsyncMock(return_value=member),
    )
    with pytest.raises(DomainError, match="项目不存在"):
        await _visible_project(
            FakeSession(scalar_values=[None]), organization_id, project_id, actor_id
        )
    with pytest.raises(DomainError, match="项目不存在"):
        await _visible_project(
            FakeSession(scalar_values=[project], get_values=[None]),
            organization_id,
            project_id,
            actor_id,
        )
    visible = await _visible_project(
        FakeSession(
            scalar_values=[project],
            get_values=[SimpleNamespace(role=ProjectRole.VIEWER)],
        ),
        organization_id,
        project_id,
        actor_id,
    )
    assert visible == (project, member)

    monkeypatch.setattr(
        "platform_api.api.projects._visible_project",
        AsyncMock(return_value=(project, member)),
    )
    with pytest.raises(DomainError, match="项目管理员"):
        await _require_project_admin(
            FakeSession(get_values=[None]), organization_id, project_id, actor_id
        )
    assert (
        await _require_project_admin(
            FakeSession(get_values=[SimpleNamespace(role=ProjectRole.ADMIN)]),
            organization_id,
            project_id,
            actor_id,
        )
        is project
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "code"),
    [
        (StaleDataError(), "VERSION_MISMATCH"),
        (IntegrityError("x", {}, None), "PROJECT_CODE_EXISTS"),
    ],
)
async def test_project_commit_maps_database_conflicts(error, code) -> None:
    project = SimpleNamespace()
    session = FakeSession()

    async def fail_commit():
        raise error

    session.commit = fail_commit
    with pytest.raises(DomainError) as caught:
        await _commit_project(session, project)
    assert caught.value.code == code
    assert session.rollbacks == 1
