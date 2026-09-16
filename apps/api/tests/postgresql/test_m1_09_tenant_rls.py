from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from platform_api.db.models import UserModel

pytestmark = [pytest.mark.asyncio, pytest.mark.postgresql]


def bearer(token: str, key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if key:
        headers["Idempotency-Key"] = key
    return headers


async def create_tenant(client, token: str, suffix: str) -> tuple[UUID, UUID]:
    organization = await client.post(
        "/api/v1/organizations",
        headers=bearer(token, f"m1-09-org-{suffix}-0001"),
        json={"name": f"Tenant {suffix}"},
    )
    assert organization.status_code == 201, organization.text
    organization_id = UUID(organization.json()["id"])
    project = await client.post(
        f"/api/v1/organizations/{organization_id}/projects",
        headers=bearer(token, f"m1-09-project-{suffix}-0001"),
        json={"code": f"tenant-{suffix}", "name": f"Project {suffix}"},
    )
    assert project.status_code == 201, project.text
    return organization_id, UUID(project.json()["id"])


async def set_context(connection, actor_id: UUID, organization_id: UUID | None) -> None:
    await connection.execute(text("SET LOCAL ROLE platform_runtime"))
    await connection.execute(
        text("select set_config('app.actor_id', :actor_id, true)"),
        {"actor_id": str(actor_id)},
    )
    await connection.execute(
        text("select set_config('app.organization_id', :organization_id, true)"),
        {"organization_id": str(organization_id) if organization_id else ""},
    )


async def test_same_connection_isolates_tenants_and_clears_context(
    postgresql_api,
) -> None:
    client = postgresql_api.client
    organization_a, project_a = await create_tenant(client, "owner-token", "a")
    organization_b, project_b = await create_tenant(client, "outsider-token", "b")

    async with postgresql_api.database.session_factory() as session:
        actor_a = await session.scalar(
            select(UserModel.id).where(UserModel.external_subject == "owner-subject")
        )
        actor_b = await session.scalar(
            select(UserModel.id).where(UserModel.external_subject == "outsider-subject")
        )
    assert actor_a and actor_b

    async with postgresql_api.database.engine.connect() as connection:
        backend_pid = await connection.scalar(text("select pg_backend_pid()"))
        await connection.commit()
        async with connection.begin():
            await set_context(connection, actor_a, organization_a)
            assert list(
                await connection.scalars(text("select id from projects order by id"))
            ) == [project_a]
            cross_update = await connection.execute(
                text("update projects set name = 'blocked' where id = :id"),
                {"id": project_b},
            )
            assert cross_update.rowcount == 0
            savepoint = await connection.begin_nested()
            with pytest.raises(DBAPIError):
                await connection.execute(
                    text(
                        "insert into projects "
                        "(id, organization_id, code, name, status, version) "
                        "values (:id, :organization_id, 'cross-write', 'Blocked', "
                        "'ACTIVE', 1)"
                    ),
                    {"id": uuid4(), "organization_id": organization_b},
                )
            await savepoint.rollback()

        async with connection.begin():
            assert (
                await connection.scalar(text("select current_user")) == "platform_test"
            )
            assert await connection.scalar(
                text("select current_setting('app.actor_id', true)")
            ) in {None, ""}
            assert await connection.scalar(
                text("select current_setting('app.organization_id', true)")
            ) in {None, ""}
            await set_context(connection, actor_b, organization_b)
            assert list(await connection.scalars(text("select id from projects"))) == [
                project_b
            ]

        transaction = await connection.begin()
        await set_context(connection, actor_a, organization_a)
        await transaction.rollback()
        async with connection.begin():
            assert (
                await connection.scalar(text("select current_user")) == "platform_test"
            )
            assert await connection.scalar(
                text("select current_setting('app.organization_id', true)")
            ) in {None, ""}
            await set_context(connection, actor_a, None)
            assert list(
                await connection.scalars(
                    text("select id from organizations order by id")
                )
            ) == [organization_a]
            assert list(await connection.scalars(text("select id from projects"))) == []
            savepoint = await connection.begin_nested()
            with pytest.raises(DBAPIError):
                await connection.execute(
                    text(
                        "insert into organization_members "
                        "(organization_id, user_id, role) "
                        "values (:organization_id, :user_id, 'MEMBER')"
                    ),
                    {"organization_id": organization_b, "user_id": actor_a},
                )
            await savepoint.rollback()
            assert (
                await connection.scalar(text("select pg_backend_pid()")) == backend_pid
            )


async def test_runtime_role_and_api_cross_tenant_matrix(postgresql_api) -> None:
    client = postgresql_api.client
    organization_a, _ = await create_tenant(client, "owner-token", "matrix-a")
    organization_b, project_b = await create_tenant(
        client, "outsider-token", "matrix-b"
    )
    denied = await client.get(
        f"/api/v1/organizations/{organization_b}/projects/{project_b}",
        headers=bearer("owner-token"),
    )
    own = await client.get(
        f"/api/v1/organizations/{organization_a}/projects",
        headers=bearer("owner-token"),
    )
    assert denied.status_code == 404
    assert own.status_code == 200

    async with postgresql_api.database.engine.connect() as connection:
        attributes = (
            await connection.execute(
                text(
                    "select rolsuper, rolbypassrls, rolcreaterole, rolcanlogin "
                    "from pg_roles where rolname = 'platform_runtime'"
                )
            )
        ).one()
        enabled = await connection.scalar(
            text(
                "select count(*) from pg_class "
                "where relname = any(:tables) and relrowsecurity"
            ),
            {
                "tables": [
                    "organizations",
                    "organization_members",
                    "organization_invites",
                    "projects",
                    "project_members",
                    "audit_events",
                    "outbox_events",
                    "upload_sessions",
                    "upload_parts",
                    "artifacts",
                ]
            },
        )
    assert attributes == (False, False, False, False)
    assert enabled == 10


async def test_m2_artifact_tables_enforce_real_postgresql_tenant_context(
    postgresql_api,
) -> None:
    client = postgresql_api.client
    organization_a, project_a = await create_tenant(
        client, "owner-token", "m2-close04-a"
    )
    organization_b, project_b = await create_tenant(
        client, "outsider-token", "m2-close04-b"
    )

    async def create_upload(token: str, organization_id: UUID, project_id: UUID):
        response = await client.post(
            f"/api/v1/organizations/{organization_id}/projects/{project_id}/upload-sessions",
            headers=bearer(token, f"m2-close04-upload-{uuid4().hex}"),
            json={
                "display_name": "matrix.bin",
                "size_bytes": 1,
                "sha256": "0" * 64,
                "content_type": "application/octet-stream",
            },
        )
        assert response.status_code == 201, response.text
        return UUID(response.json()["id"])

    upload_a = await create_upload("owner-token", organization_a, project_a)
    upload_b = await create_upload("outsider-token", organization_b, project_b)
    async with postgresql_api.database.session_factory() as session:
        actor_a = await session.scalar(
            select(UserModel.id).where(UserModel.external_subject == "owner-subject")
        )
        actor_b = await session.scalar(
            select(UserModel.id).where(UserModel.external_subject == "outsider-subject")
        )
    assert actor_a and actor_b

    artifacts: dict[UUID, UUID] = {}
    for organization_id, project_id, actor_id, upload_id, status in (
        (organization_a, project_a, actor_a, upload_a, "AVAILABLE"),
        (organization_b, project_b, actor_b, upload_b, "QUARANTINED"),
    ):
        artifact_id = uuid4()
        artifacts[organization_id] = artifact_id
        async with postgresql_api.database.engine.begin() as connection:
            await set_context(connection, actor_id, organization_id)
            object_key = await connection.scalar(
                text("select object_key from upload_sessions where id = :id"),
                {"id": upload_id},
            )
            assert object_key
            await connection.execute(
                text(
                    "insert into artifacts "
                    "(id, upload_session_id, organization_id, project_id, created_by, "
                    "display_name, object_key, bucket_alias, size_bytes, expected_sha256, "
                    "verified_sha256, declared_content_type, detected_content_type, "
                    "integrity_status, security_scan_status, status) values "
                    "(:id, :upload_id, :organization_id, :project_id, :created_by, "
                    "'matrix.bin', :object_key, 'primary', 1, :sha256, :sha256, "
                    "'application/octet-stream', 'application/octet-stream', "
                    "'VERIFIED', 'NOT_REQUIRED', :status)"
                ),
                {
                    "id": artifact_id,
                    "upload_id": upload_id,
                    "organization_id": organization_id,
                    "project_id": project_id,
                    "created_by": actor_id,
                    "object_key": object_key,
                    "sha256": "0" * 64,
                    "status": status,
                },
            )

    async with postgresql_api.database.engine.connect() as connection:
        for organization_id, actor_id, upload_id in (
            (organization_a, actor_a, upload_a),
            (organization_b, actor_b, upload_b),
        ):
            async with connection.begin():
                await set_context(connection, actor_id, organization_id)
                assert list(
                    await connection.scalars(text("select id from upload_sessions"))
                ) == [upload_id]
                assert list(
                    await connection.scalars(text("select id from artifacts"))
                ) == [artifacts[organization_id]]
        async with connection.begin():
            await set_context(connection, actor_a, None)
            assert list(await connection.scalars(text("select id from upload_sessions"))) == []
            assert list(await connection.scalars(text("select id from artifacts"))) == []

    hidden = await client.get(
        f"/api/v1/organizations/{organization_a}/projects/{project_a}/upload-sessions/{upload_a}",
        headers=bearer("outsider-token"),
    )
    assert hidden.status_code == 404
