import uuid

import pytest
from sqlalchemy import func, select

from platform_api.db.models import OrganizationInviteModel, OrganizationMemberModel

pytestmark = [pytest.mark.asyncio, pytest.mark.postgresql]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": uuid.uuid4().hex}


async def test_invitation_and_owner_admin_member_rbac_matrix(postgresql_api) -> None:
    client = postgresql_api.client
    organization = await client.post(
        "/api/v1/organizations",
        headers=bearer("owner-token"),
        json={"name": "M1-05 RBAC"},
    )
    assert organization.status_code == 201
    organization_id = organization.json()["id"]
    invites = f"/api/v1/organizations/{organization_id}/invites"
    members = f"/api/v1/organizations/{organization_id}/members"
    projects = f"/api/v1/organizations/{organization_id}/projects"

    admin_invite = await client.post(
        invites,
        headers=bearer("owner-token"),
        json={"email": "admin@example.com", "role": "ADMIN"},
    )
    assert admin_invite.status_code == 201
    admin_token = admin_invite.json()["token"]
    assert len(admin_token) >= 32

    accepted_admin = await client.post(
        f"/api/v1/invites/{admin_token}/accept",
        headers=bearer("admin-token"),
    )
    assert accepted_admin.status_code == 201
    admin_id = accepted_admin.json()["user_id"]

    member_invite = await client.post(
        invites,
        headers=bearer("admin-token"),
        json={"email": "member@example.com", "role": "MEMBER"},
    )
    assert member_invite.status_code == 201
    member_token = member_invite.json()["token"]
    accepted_member = await client.post(
        f"/api/v1/invites/{member_token}/accept",
        headers=bearer("member-token"),
    )
    assert accepted_member.status_code == 201
    member_id = accepted_member.json()["user_id"]

    listing = await client.get(members, headers=bearer("member-token"))
    assert listing.status_code == 200
    assert {item["role"] for item in listing.json()} == {
        "OWNER",
        "ADMIN",
        "MEMBER",
    }

    member_cannot_invite = await client.post(
        invites,
        headers=bearer("member-token"),
        json={"email": "blocked@example.com", "role": "MEMBER"},
    )
    member_cannot_create_project = await client.post(
        projects,
        headers=bearer("member-token"),
        json={"code": "member-denied", "name": "Denied"},
    )
    assert member_cannot_invite.status_code == 403
    assert member_cannot_create_project.status_code == 403

    admin_project = await client.post(
        projects,
        headers=bearer("admin-token"),
        json={"code": "admin-allowed", "name": "Allowed"},
    )
    assert admin_project.status_code == 201

    promoted = await client.patch(
        f"{members}/{member_id}",
        headers=bearer("admin-token"),
        json={"role": "ADMIN"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "ADMIN"

    owner_id = next(
        item["user_id"] for item in listing.json() if item["role"] == "OWNER"
    )
    owner_change_denied = await client.patch(
        f"{members}/{owner_id}",
        headers=bearer("admin-token"),
        json={"role": "MEMBER"},
    )
    assert owner_change_denied.status_code == 403

    removed = await client.delete(
        f"{members}/{member_id}",
        headers=bearer("owner-token"),
    )
    assert removed.status_code == 204
    removed_access = await client.get(projects, headers=bearer("member-token"))
    assert removed_access.status_code == 404

    replay = await client.post(
        f"/api/v1/invites/{admin_token}/accept",
        headers=bearer("admin-token"),
    )
    assert replay.status_code == 409

    async with postgresql_api.database.session_factory() as session:
        invite_hashes = (
            await session.scalars(select(OrganizationInviteModel.token_hash))
        ).all()
        membership_count = await session.scalar(
            select(func.count()).select_from(OrganizationMemberModel)
        )
    assert invite_hashes
    assert all(isinstance(value, bytes) and len(value) == 32 for value in invite_hashes)
    assert membership_count == 2
    assert admin_id != member_id


async def test_invite_email_revoke_and_expiry_guards(postgresql_api) -> None:
    from datetime import UTC, datetime, timedelta

    client = postgresql_api.client
    organization = await client.post(
        "/api/v1/organizations",
        headers=bearer("owner-token"),
        json={"name": "M1-05 Guards"},
    )
    organization_id = organization.json()["id"]
    endpoint = f"/api/v1/organizations/{organization_id}/invites"

    created = await client.post(
        endpoint,
        headers=bearer("owner-token"),
        json={"email": "member@example.com", "role": "MEMBER"},
    )
    invite_id = created.json()["id"]
    token = created.json()["token"]

    mismatch = await client.post(
        f"/api/v1/invites/{token}/accept",
        headers=bearer("outsider-token"),
    )
    assert mismatch.status_code == 403
    assert mismatch.json()["code"] == "INVITE_EMAIL_MISMATCH"

    listing = await client.get(endpoint, headers=bearer("owner-token"))
    assert listing.status_code == 200
    assert "token" not in listing.json()[0]

    revoked = await client.delete(
        f"{endpoint}/{invite_id}",
        headers=bearer("owner-token"),
    )
    rejected = await client.post(
        f"/api/v1/invites/{token}/accept",
        headers=bearer("member-token"),
    )
    assert revoked.status_code == 204
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "INVITE_REVOKED"

    reissued = await client.post(
        endpoint,
        headers=bearer("owner-token"),
        json={"email": "member@example.com", "role": "MEMBER"},
    )
    new_token = reissued.json()["token"]
    async with postgresql_api.database.session_factory() as session:
        invite = await session.scalar(
            select(OrganizationInviteModel).where(
                OrganizationInviteModel.id == reissued.json()["id"]
            )
        )
        invite.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    expired = await client.post(
        f"/api/v1/invites/{new_token}/accept",
        headers=bearer("member-token"),
    )
    assert expired.status_code == 409
    assert expired.json()["code"] == "INVITE_EXPIRED"
