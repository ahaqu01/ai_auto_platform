from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Response
from sqlalchemy.exc import IntegrityError

import platform_api.api.organizations as organizations_api
import platform_api.api.projects as projects_api
from platform_api.common.errors import DomainError
from platform_api.modules.organization.domain import OrganizationRole


class FakeSession:
    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    def __init__(self, *, scalar_values=(), get_values=()) -> None:
        self.scalar_values = list(scalar_values)
        self.get_values = list(get_values)
        self.added = []
        self.deleted = []
        self.rollbacks = 0

    async def scalar(self, _statement):
        return self.scalar_values.pop(0)

    async def get(self, _model, _key):
        return self.get_values.pop(0)

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, _value):
        return None

    async def delete(self, value):
        self.deleted.append(value)


def invite_record(**overrides):
    now = organizations_api.datetime.now(organizations_api.UTC)
    values = {
        "id": uuid4(),
        "organization_id": uuid4(),
        "email": "user@example.com",
        "role": OrganizationRole.MEMBER,
        "expires_at": now + organizations_api.timedelta(days=1),
        "accepted_at": None,
        "revoked_at": None,
        "token_hash": b"hash",
        "invited_by": uuid4(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def current_user(email="user@example.com"):
    return SimpleNamespace(id=uuid4(), email=email, display_name="User")


def request():
    return SimpleNamespace(state=SimpleNamespace(trace_id="test-trace"))


def test_invite_models_normalize_and_reject_invalid_addresses() -> None:
    payload = organizations_api.InviteCreate(email=" User@Example.COM ", role="MEMBER")
    assert payload.email == "user@example.com"
    for value in ("missing-at", "@host", "user@", "a@b@c"):
        with pytest.raises(ValueError):
            organizations_api.InviteCreate(email=value, role="MEMBER")
    invite = invite_record()
    assert type(organizations_api._invite_read(invite)).__name__ == "InviteRead"
    assert organizations_api._invite_read(invite, "token").token == "token"


@pytest.mark.asyncio
async def test_create_invite_conflict_reissue_and_database_race(monkeypatch) -> None:
    monkeypatch.setattr(organizations_api, "require_organization_admin", AsyncMock())
    organization_id = uuid4()
    actor = current_user()
    payload = organizations_api.InviteCreate(email=actor.email, role="MEMBER")
    with pytest.raises(DomainError) as existing_member:
        await organizations_api.create_invite(
            organization_id,
            payload,
            actor,
            FakeSession(scalar_values=[object()]),
            request(),
        )
    assert existing_member.value.code == "MEMBER_ALREADY_EXISTS"

    active = invite_record(organization_id=organization_id)
    with pytest.raises(DomainError) as duplicate:
        await organizations_api.create_invite(
            organization_id,
            payload,
            actor,
            FakeSession(scalar_values=[None, active]),
            request(),
        )
    assert duplicate.value.code == "INVITE_ALREADY_EXISTS"

    expired = invite_record(
        organization_id=organization_id,
        expires_at=organizations_api.datetime.now(organizations_api.UTC)
        - organizations_api.timedelta(seconds=1),
    )
    created = await organizations_api.create_invite(
        organization_id,
        payload,
        actor,
        FakeSession(scalar_values=[None, expired]),
        request(),
    )
    assert created.email == actor.email and created.token

    racing = FakeSession(
        scalar_values=[
            None,
            invite_record(
                organization_id=organization_id,
                expires_at=organizations_api.datetime.now(organizations_api.UTC)
                - organizations_api.timedelta(seconds=1),
            ),
        ]
    )

    async def conflict():
        raise IntegrityError("insert", {}, None)

    racing.commit = conflict
    with pytest.raises(DomainError) as race:
        await organizations_api.create_invite(
            organization_id, payload, actor, racing, request()
        )
    assert race.value.code == "INVITE_CONFLICT" and racing.rollbacks == 1


@pytest.mark.asyncio
async def test_revoke_and_accept_invite_guard_matrix(monkeypatch) -> None:
    monkeypatch.setattr(organizations_api, "require_organization_admin", AsyncMock())
    monkeypatch.setattr(organizations_api, "resolve_invite_tenant", AsyncMock())
    organization_id, invite_id = uuid4(), uuid4()
    actor = current_user()
    with pytest.raises(DomainError) as missing:
        await organizations_api.revoke_invite(
            organization_id,
            invite_id,
            actor,
            FakeSession(scalar_values=[None]),
            request(),
        )
    assert missing.value.code == "INVITE_NOT_FOUND"
    accepted = invite_record(
        accepted_at=organizations_api.datetime.now(organizations_api.UTC)
    )
    with pytest.raises(DomainError) as already:
        await organizations_api.revoke_invite(
            organization_id,
            invite_id,
            actor,
            FakeSession(scalar_values=[accepted]),
            request(),
        )
    assert already.value.code == "INVITE_ALREADY_ACCEPTED"
    response = await organizations_api.revoke_invite(
        organization_id,
        invite_id,
        actor,
        FakeSession(scalar_values=[invite_record()]),
        request(),
    )
    assert response.status_code == 204

    cases = [
        (None, "INVITE_NOT_FOUND"),
        (
            invite_record(
                accepted_at=organizations_api.datetime.now(organizations_api.UTC)
            ),
            "INVITE_ALREADY_ACCEPTED",
        ),
        (
            invite_record(
                revoked_at=organizations_api.datetime.now(organizations_api.UTC)
            ),
            "INVITE_REVOKED",
        ),
        (
            invite_record(
                expires_at=organizations_api.datetime.now(organizations_api.UTC)
                - organizations_api.timedelta(seconds=1)
            ),
            "INVITE_EXPIRED",
        ),
        (invite_record(email="other@example.com"), "INVITE_EMAIL_MISMATCH"),
    ]
    for invite, code in cases:
        with pytest.raises(DomainError) as error:
            await organizations_api.accept_invite(
                "token", actor, FakeSession(scalar_values=[invite]), request()
            )
        assert error.value.code == code

    valid = invite_record(email=actor.email)
    result = await organizations_api.accept_invite(
        "token", actor, FakeSession(scalar_values=[valid]), request()
    )
    assert result.email == actor.email and valid.accepted_at is not None
    racing = FakeSession(scalar_values=[invite_record(email=actor.email)])

    async def conflict():
        raise IntegrityError("insert", {}, None)

    racing.commit = conflict
    with pytest.raises(DomainError) as race:
        await organizations_api.accept_invite("token", actor, racing, request())
    assert race.value.code == "MEMBER_ALREADY_EXISTS" and racing.rollbacks == 1


def project_record(**overrides):
    values = {
        "id": uuid4(),
        "organization_id": uuid4(),
        "code": "project",
        "name": "Project",
        "description": None,
        "status": projects_api.ProjectStatus.ACTIVE,
        "version": 1,
        "archived_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_project_payload_normalization_and_change_requirement() -> None:
    assert projects_api.ProjectCreate(code="demo", name="Demo").code == "demo"
    assert projects_api.ProjectUpdate(code="next").code == "next"
    assert projects_api.ProjectUpdate(name="Next").code is None
    with pytest.raises(ValueError, match="at least one"):
        projects_api.ProjectUpdate()


@pytest.mark.asyncio
async def test_create_project_permission_replay_and_flush_conflict(monkeypatch) -> None:
    actor = current_user()
    organization_id = uuid4()
    payload = projects_api.ProjectCreate(
        code="demo", name=" Demo ", description=" text "
    )
    response = Response()
    request = SimpleNamespace(state=SimpleNamespace(trace_id="trace"))
    monkeypatch.setattr(
        projects_api,
        "require_organization_member",
        AsyncMock(return_value=SimpleNamespace(role=OrganizationRole.MEMBER)),
    )
    with pytest.raises(DomainError) as denied:
        await projects_api.create_project(
            organization_id, payload, actor, FakeSession(), response, request
        )
    assert denied.value.code == "ORGANIZATION_ADMIN_REQUIRED"
    monkeypatch.setattr(
        projects_api,
        "require_organization_member",
        AsyncMock(return_value=SimpleNamespace(role=OrganizationRole.ADMIN)),
    )
    monkeypatch.setattr(
        projects_api,
        "begin_idempotent_command",
        AsyncMock(
            return_value=SimpleNamespace(
                is_replay=True, replay_status=201, replay_body={"id": "replayed"}
            )
        ),
    )
    replay = await projects_api.create_project(
        organization_id, payload, actor, FakeSession(), response, request
    )
    assert replay.headers["Idempotent-Replayed"] == "true"
    monkeypatch.setattr(
        projects_api,
        "begin_idempotent_command",
        AsyncMock(return_value=SimpleNamespace(is_replay=False)),
    )
    session = FakeSession()

    async def conflict():
        raise IntegrityError("insert", {}, None)

    session.flush = conflict
    with pytest.raises(DomainError) as race:
        await projects_api.create_project(
            organization_id, payload, actor, session, response, request
        )
    assert race.value.code == "PROJECT_CODE_EXISTS" and session.rollbacks == 1


@pytest.mark.asyncio
async def test_project_update_field_matrix_and_status_events(monkeypatch) -> None:
    project = project_record()
    actor = current_user()
    monkeypatch.setattr(
        projects_api, "_require_project_admin", AsyncMock(return_value=project)
    )
    monkeypatch.setattr(
        projects_api, "_commit_project", AsyncMock(return_value=project)
    )
    response = Response()
    updated = await projects_api.update_project(
        project.organization_id,
        project.id,
        projects_api.ProjectUpdate(code="next", name=" Next ", description=" detail "),
        actor,
        FakeSession(),
        response,
        '"1"',
    )
    assert (updated.code, updated.name, updated.description) == (
        "next",
        "Next",
        "detail",
    )
    await projects_api.update_project(
        project.organization_id,
        project.id,
        projects_api.ProjectUpdate(description=None),
        actor,
        FakeSession(),
        response,
        '"1"',
    )
    assert project.description is None
    monkeypatch.setattr(projects_api, "record_audit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(projects_api, "record_outbox", lambda *_args, **_kwargs: None)
    changed = await projects_api._change_status(
        FakeSession(),
        project,
        projects_api.ProjectStatus.ARCHIVED,
        '"1"',
        actor.id,
        None,
    )
    assert changed.archived_at is not None
    changed = await projects_api._change_status(
        FakeSession(), project, projects_api.ProjectStatus.ACTIVE, '"1"', actor.id, None
    )
    assert changed.archived_at is None


@pytest.mark.asyncio
async def test_project_member_missing_and_conflict_guards(monkeypatch) -> None:
    monkeypatch.setattr(
        projects_api, "_require_project_admin", AsyncMock(return_value=project_record())
    )
    organization_id, project_id, member_id = uuid4(), uuid4(), uuid4()
    actor = current_user()
    create = projects_api.ProjectMemberCreate(member_id=member_id, role="VIEWER")
    with pytest.raises(DomainError) as outsider:
        await projects_api.add_project_member(
            organization_id,
            project_id,
            create,
            actor,
            FakeSession(get_values=[None]),
            request(),
        )
    assert outsider.value.code == "ORGANIZATION_MEMBER_REQUIRED"
    session = FakeSession(get_values=[object()])

    async def conflict():
        raise IntegrityError("insert", {}, None)

    session.commit = conflict
    with pytest.raises(DomainError) as duplicate:
        await projects_api.add_project_member(
            organization_id, project_id, create, actor, session, request()
        )
    assert duplicate.value.code == "PROJECT_MEMBER_EXISTS"
    update = projects_api.ProjectMemberUpdate(role="ADMIN")
    with pytest.raises(DomainError) as missing_update:
        await projects_api.update_project_member(
            organization_id,
            project_id,
            member_id,
            update,
            actor,
            FakeSession(get_values=[None]),
            request(),
        )
    assert missing_update.value.code == "PROJECT_MEMBER_NOT_FOUND"
    with pytest.raises(DomainError) as missing_remove:
        await projects_api.remove_project_member(
            organization_id,
            project_id,
            member_id,
            actor,
            FakeSession(get_values=[None]),
            request(),
        )
    assert missing_remove.value.code == "PROJECT_MEMBER_NOT_FOUND"
