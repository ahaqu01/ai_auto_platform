import asyncio
import uuid

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.postgresql]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": uuid.uuid4().hex}


async def invite(
    client,
    organization_id: str,
    actor: str,
    email: str,
    token: str,
    role: str = "MEMBER",
) -> str:
    created = await client.post(
        f"/api/v1/organizations/{organization_id}/invites",
        headers=bearer(actor),
        json={"email": email, "role": role},
    )
    assert created.status_code == 201
    accepted = await client.post(
        f"/api/v1/invites/{created.json()['token']}/accept", headers=bearer(token)
    )
    assert accepted.status_code == 201
    return accepted.json()["user_id"]


async def setup_organization(postgresql_api):
    client = postgresql_api.client
    created = await client.post(
        "/api/v1/organizations",
        headers=bearer("owner-token"),
        json={"name": "M1-07 Projects"},
    )
    assert created.status_code == 201
    organization_id = created.json()["id"]
    admin_id = await invite(
        client,
        organization_id,
        "owner-token",
        "admin@example.com",
        "admin-token",
        "ADMIN",
    )
    member_id = await invite(
        client, organization_id, "admin-token", "member@example.com", "member-token"
    )
    return client, organization_id, admin_id, member_id


async def test_project_crud_archive_restore_members_and_visibility(
    postgresql_api,
) -> None:
    client, organization_id, _, member_id = await setup_organization(postgresql_api)
    collection = f"/api/v1/organizations/{organization_id}/projects"
    created = await client.post(
        collection,
        headers=bearer("admin-token"),
        json={"code": "project-one", "name": "Project One", "description": "initial"},
    )
    assert created.status_code == 201
    assert created.json()["version"] == 1
    assert created.headers["etag"] == '"1"'
    project_id = created.json()["id"]
    project = f"{collection}/{project_id}"

    hidden = await client.get(project, headers=bearer("member-token"))
    assert hidden.status_code == 404
    assert (await client.get(collection, headers=bearer("member-token"))).json() == []

    added = await client.post(
        f"{project}/members",
        headers=bearer("admin-token"),
        json={"member_id": member_id, "role": "VIEWER"},
    )
    assert added.status_code == 201
    assert added.json()["role"] == "VIEWER"
    assert (
        await client.get(project, headers=bearer("member-token"))
    ).status_code == 200

    denied = await client.patch(
        f"{project}/members/{member_id}",
        headers=bearer("member-token"),
        json={"role": "ADMIN"},
    )
    assert denied.status_code == 403
    outsider = await client.post(
        f"{project}/members",
        headers=bearer("admin-token"),
        json={"member_id": "00000000-0000-0000-0000-000000000001", "role": "VIEWER"},
    )
    assert outsider.status_code == 409
    assert outsider.json()["code"] == "ORGANIZATION_MEMBER_REQUIRED"

    missing_precondition = await client.patch(
        project, headers=bearer("admin-token"), json={"name": "No version"}
    )
    assert missing_precondition.status_code == 428
    updated = await client.patch(
        project,
        headers={**bearer("admin-token"), "If-Match": '"1"'},
        json={"name": "Updated", "description": None},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    stale = await client.patch(
        project,
        headers={**bearer("admin-token"), "If-Match": '"1"'},
        json={"name": "Stale"},
    )
    assert stale.status_code == 412
    assert stale.json()["code"] == "VERSION_MISMATCH"

    archived = await client.post(
        f"{project}:archive",
        headers={**bearer("admin-token"), "If-Match": '"2"'},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "ARCHIVED"
    assert (
        await client.get(project, headers=bearer("member-token"))
    ).status_code == 200
    restored = await client.post(
        f"{project}:restore",
        headers={**bearer("admin-token"), "If-Match": '"3"'},
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "ACTIVE"
    deleted = await client.delete(
        project, headers={**bearer("admin-token"), "If-Match": '"4"'}
    )
    assert deleted.status_code == 204
    assert (await client.get(project, headers=bearer("admin-token"))).status_code == 404


async def test_project_cursor_pagination_is_complete(postgresql_api) -> None:
    client, organization_id, _, _ = await setup_organization(postgresql_api)
    collection = f"/api/v1/organizations/{organization_id}/projects"
    created_ids = []
    for index in range(3):
        response = await client.post(
            collection,
            headers=bearer("admin-token"),
            json={"code": f"page-{index}", "name": f"Page {index}"},
        )
        assert response.status_code == 201
        created_ids.append(response.json()["id"])
    first = await client.get(f"{collection}?limit=2", headers=bearer("admin-token"))
    assert first.status_code == 200
    assert len(first.json()) == 2
    cursor = first.headers["x-next-cursor"]
    assert "{" not in cursor and created_ids[0] not in cursor
    second = await client.get(
        f"{collection}?limit=2&cursor={cursor}", headers=bearer("admin-token")
    )
    assert second.status_code == 200
    returned = [item["id"] for item in first.json() + second.json()]
    assert returned == created_ids
    assert len(set(returned)) == 3


async def test_same_project_version_allows_only_one_concurrent_update(
    postgresql_api,
) -> None:
    client, organization_id, _, _ = await setup_organization(postgresql_api)
    collection = f"/api/v1/organizations/{organization_id}/projects"
    created = await client.post(
        collection,
        headers=bearer("admin-token"),
        json={"code": "optimistic", "name": "Optimistic"},
    )
    project = f"{collection}/{created.json()['id']}"

    async def update(name: str):
        response = await client.patch(
            project,
            headers={**bearer("admin-token"), "If-Match": '"1"'},
            json={"name": name},
        )
        return response.status_code, response.json().get("code")

    outcomes = await asyncio.gather(update("Winner A"), update("Winner B"))
    assert sorted(status for status, _ in outcomes) == [200, 412]
    current = await client.get(project, headers=bearer("admin-token"))
    assert current.json()["version"] == 2
