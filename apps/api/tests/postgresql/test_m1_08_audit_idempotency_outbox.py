import asyncio

import pytest
from sqlalchemy import func, select

from platform_api.db.models import (
    AuditEventModel,
    IdempotencyRecordModel,
    OrganizationModel,
    OutboxEventModel,
    ProjectModel,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.postgresql]


def bearer(token: str, key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


async def test_organization_idempotency_replay_and_conflict(postgresql_api) -> None:
    client = postgresql_api.client
    headers = bearer("owner-token", "organization-create-key-0001")
    first = await client.post(
        "/api/v1/organizations", headers=headers, json={"name": "Idempotent Org"}
    )
    replay = await client.post(
        "/api/v1/organizations", headers=headers, json={"name": "Idempotent Org"}
    )
    conflict = await client.post(
        "/api/v1/organizations", headers=headers, json={"name": "Different Org"}
    )
    missing = await client.post(
        "/api/v1/organizations",
        headers=bearer("owner-token"),
        json={"name": "No Key"},
    )

    assert first.status_code == replay.status_code == 201
    assert first.json() == replay.json()
    assert first.headers["idempotent-replayed"] == "false"
    assert replay.headers["idempotent-replayed"] == "true"
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert missing.status_code == 428
    assert missing.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"

    async with postgresql_api.database.session_factory() as session:
        assert (
            await session.scalar(select(func.count()).select_from(OrganizationModel))
            == 1
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(IdempotencyRecordModel)
            )
            == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(AuditEventModel)) == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(OutboxEventModel))
            == 1
        )


async def test_concurrent_project_replay_creates_one_transactional_result(
    postgresql_api,
) -> None:
    client = postgresql_api.client
    organization = await client.post(
        "/api/v1/organizations",
        headers=bearer("owner-token", "organization-create-key-0002"),
        json={"name": "Concurrent Project Org"},
    )
    organization_id = organization.json()["id"]
    endpoint = f"/api/v1/organizations/{organization_id}/projects"
    headers = bearer("owner-token", "project-create-key-0000001")
    payload = {"code": "idempotent-project", "name": "Idempotent Project"}

    first, second = await asyncio.gather(
        client.post(endpoint, headers=headers, json=payload),
        client.post(endpoint, headers=headers, json=payload),
    )
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert sorted(
        [first.headers["idempotent-replayed"], second.headers["idempotent-replayed"]]
    ) == ["false", "true"]

    async with postgresql_api.database.session_factory() as session:
        project_count = await session.scalar(
            select(func.count()).select_from(ProjectModel)
        )
        project_audits = await session.scalar(
            select(func.count())
            .select_from(AuditEventModel)
            .where(AuditEventModel.action == "project.create")
        )
        project_events = await session.scalar(
            select(func.count())
            .select_from(OutboxEventModel)
            .where(OutboxEventModel.event_type == "ProjectCreated.v1")
        )
    assert (project_count, project_audits, project_events) == (1, 1, 1)


async def test_failed_command_rolls_back_idempotency_audit_and_outbox(
    postgresql_api,
) -> None:
    client = postgresql_api.client
    organization = await client.post(
        "/api/v1/organizations",
        headers=bearer("owner-token", "organization-create-key-0003"),
        json={"name": "Rollback Org"},
    )
    organization_id = organization.json()["id"]
    endpoint = f"/api/v1/organizations/{organization_id}/projects"
    payload = {"code": "duplicate-on-rollback", "name": "First"}
    first = await client.post(
        endpoint,
        headers=bearer("owner-token", "project-success-key-00001"),
        json=payload,
    )
    failed_key = "project-failure-key-00001"
    failed = await client.post(
        endpoint,
        headers=bearer("owner-token", failed_key),
        json={"code": payload["code"], "name": "Conflicting"},
    )
    assert first.status_code == 201
    assert failed.status_code == 409
    assert failed.json()["code"] == "PROJECT_CODE_EXISTS"

    async with postgresql_api.database.session_factory() as session:
        failed_records = await session.scalar(
            select(func.count())
            .select_from(IdempotencyRecordModel)
            .where(IdempotencyRecordModel.idempotency_key == failed_key)
        )
        project_count = await session.scalar(
            select(func.count()).select_from(ProjectModel)
        )
        project_audits = await session.scalar(
            select(func.count())
            .select_from(AuditEventModel)
            .where(AuditEventModel.action == "project.create")
        )
        project_events = await session.scalar(
            select(func.count())
            .select_from(OutboxEventModel)
            .where(OutboxEventModel.event_type == "ProjectCreated.v1")
        )
    assert failed_records == 0
    assert (project_count, project_audits, project_events) == (1, 1, 1)


async def test_archive_and_member_remove_write_audit_and_outbox(postgresql_api) -> None:
    client = postgresql_api.client
    organization = await client.post(
        "/api/v1/organizations",
        headers=bearer("owner-token", "organization-create-key-0004"),
        json={"name": "Lifecycle Events Org"},
    )
    organization_id = organization.json()["id"]
    project = await client.post(
        f"/api/v1/organizations/{organization_id}/projects",
        headers=bearer("owner-token", "project-create-key-0000002"),
        json={"code": "event-project", "name": "Event Project"},
    )
    project_id = project.json()["id"]
    invite = await client.post(
        f"/api/v1/organizations/{organization_id}/invites",
        headers=bearer("owner-token"),
        json={"email": "member@example.com", "role": "MEMBER"},
    )
    accepted = await client.post(
        f"/api/v1/invites/{invite.json()['token']}/accept",
        headers=bearer("member-token"),
    )
    member_id = accepted.json()["user_id"]
    member_endpoint = (
        f"/api/v1/organizations/{organization_id}/projects/{project_id}/members"
    )
    added = await client.post(
        member_endpoint,
        headers=bearer("owner-token"),
        json={"member_id": member_id, "role": "VIEWER"},
    )
    changed = await client.patch(
        f"{member_endpoint}/{member_id}",
        headers=bearer("owner-token"),
        json={"role": "EDITOR"},
    )
    removed_from_project = await client.delete(
        f"{member_endpoint}/{member_id}", headers=bearer("owner-token")
    )
    changed_in_organization = await client.patch(
        f"/api/v1/organizations/{organization_id}/members/{member_id}",
        headers=bearer("owner-token"),
        json={"role": "ADMIN"},
    )
    revoked_invite = await client.post(
        f"/api/v1/organizations/{organization_id}/invites",
        headers=bearer("owner-token"),
        json={"email": "outsider@example.com", "role": "MEMBER"},
    )
    revoked = await client.delete(
        f"/api/v1/organizations/{organization_id}/invites/"
        f"{revoked_invite.json()['id']}",
        headers=bearer("owner-token"),
    )
    assert added.status_code == 201
    assert changed.status_code == 200
    assert removed_from_project.status_code == 204
    assert changed_in_organization.status_code == 200
    assert revoked.status_code == 204
    archived = await client.post(
        f"/api/v1/organizations/{organization_id}/projects/{project_id}:archive",
        headers={**bearer("owner-token"), "If-Match": '"1"'},
    )
    removed = await client.delete(
        f"/api/v1/organizations/{organization_id}/members/{member_id}",
        headers=bearer("owner-token"),
    )
    assert archived.status_code == 200
    assert removed.status_code == 204

    async with postgresql_api.database.session_factory() as session:
        actions = set(await session.scalars(select(AuditEventModel.action)))
        event_types = set(await session.scalars(select(OutboxEventModel.event_type)))
        details = list(await session.scalars(select(AuditEventModel.detail)))
        payloads = list(await session.scalars(select(OutboxEventModel.payload)))
    assert {
        "organization.invite.create",
        "organization.invite.accept",
        "organization.invite.revoke",
        "organization.member.role.update",
        "organization.member.remove",
        "project.member.add",
        "project.member.role.update",
        "project.member.remove",
        "project.archive",
    } <= actions
    assert {
        "OrganizationInviteCreated.v1",
        "OrganizationInviteAccepted.v1",
        "OrganizationInviteRevoked.v1",
        "OrganizationMemberRoleChanged.v1",
        "OrganizationMemberRemoved.v1",
        "ProjectMemberAdded.v1",
        "ProjectMemberRoleChanged.v1",
        "ProjectMemberRemoved.v1",
        "ProjectArchived.v1",
    } <= event_types
    serialized = str(details + payloads).casefold()
    assert (
        "token" not in serialized
        and "password" not in serialized
        and "cookie" not in serialized
    )
