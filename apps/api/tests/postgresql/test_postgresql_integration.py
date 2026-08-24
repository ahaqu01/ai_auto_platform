import asyncio

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from platform_api.db.models import (
    OrganizationMemberModel,
    OrganizationModel,
    ProjectModel,
    UserModel,
)
from platform_api.modules.organization.domain import OrganizationRole

pytestmark = [pytest.mark.asyncio, pytest.mark.postgresql]


async def test_fixture_runs_all_head_migrations_in_isolated_postgresql_schema(
    postgresql_database,
) -> None:
    async with postgresql_database.engine.connect() as connection:
        dialect = connection.dialect.name
        search_path = await connection.scalar(text("select current_schema()"))
        result = await connection.execute(
            text("select version_num from alembic_version")
        )
        revisions = frozenset(result.scalars())

    assert dialect == "postgresql"
    assert search_path == postgresql_database.schema
    assert revisions == frozenset(postgresql_database.head_revisions)


async def test_concurrent_project_code_insert_has_single_named_unique_violation(
    postgresql_database,
) -> None:
    async with postgresql_database.session_factory() as session:
        organization = OrganizationModel(name="并发约束企业")
        session.add(organization)
        await session.commit()
        organization_id = organization.id

    async def insert_project(name: str) -> tuple[str, str | None, str | None]:
        async with postgresql_database.session_factory() as session:
            session.add(
                ProjectModel(
                    organization_id=organization_id,
                    code="same-code",
                    name=name,
                )
            )
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                sqlstate = getattr(exc.orig, "sqlstate", None)
                diagnostic = getattr(exc.orig, "diag", None)
                constraint = getattr(diagnostic, "constraint_name", None)
                return "conflict", sqlstate, constraint
            return "committed", None, None

    outcomes = await asyncio.gather(insert_project("项目一"), insert_project("项目二"))

    committed = [outcome for outcome in outcomes if outcome[0] == "committed"]
    conflicts = [outcome for outcome in outcomes if outcome[0] == "conflict"]
    assert len(committed) == 1
    assert conflicts == [("conflict", "23505", "uq_projects_organization_id")]

    async with postgresql_database.session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(ProjectModel))
    assert count == 1


async def test_transaction_rollback_leaves_no_organization(postgresql_database) -> None:
    async with postgresql_database.session_factory() as session:
        session.add(OrganizationModel(name="应回滚企业"))
        await session.flush()
        await session.rollback()

    async with postgresql_database.session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(OrganizationModel)
        )
    assert count == 0


async def test_foreign_keys_cascade_members_and_projects(postgresql_database) -> None:
    async with postgresql_database.session_factory() as session:
        user = UserModel(email="cascade@example.com", display_name="Cascade User")
        organization = OrganizationModel(name="级联删除企业")
        session.add_all([user, organization])
        await session.flush()
        session.add_all(
            [
                OrganizationMemberModel(
                    organization_id=organization.id,
                    user_id=user.id,
                    role=OrganizationRole.OWNER,
                ),
                ProjectModel(
                    organization_id=organization.id,
                    code="cascade-project",
                    name="级联项目",
                ),
            ]
        )
        await session.commit()
        organization_id = organization.id

    async with postgresql_database.session_factory() as session:
        await session.execute(
            delete(OrganizationModel).where(OrganizationModel.id == organization_id)
        )
        await session.commit()

    async with postgresql_database.session_factory() as session:
        member_count = await session.scalar(
            select(func.count()).select_from(OrganizationMemberModel)
        )
        project_count = await session.scalar(
            select(func.count()).select_from(ProjectModel)
        )
    assert member_count == 0
    assert project_count == 0
