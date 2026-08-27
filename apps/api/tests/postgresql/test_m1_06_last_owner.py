import asyncio

import pytest
from sqlalchemy import func, select

from platform_api.api.organization_access import (
    change_member_role,
    remove_organization_member,
)
from platform_api.common.errors import DomainError
from platform_api.db.models import OrganizationMemberModel, OrganizationModel, UserModel
from platform_api.modules.organization.domain import OrganizationRole

pytestmark = [pytest.mark.asyncio, pytest.mark.postgresql]


async def _two_owner_org(db):
    async with db.session_factory() as session:
        users = [
            UserModel(email=f"owner-{i}@example.com", display_name=f"Owner {i}")
            for i in range(2)
        ]
        org = OrganizationModel(name="Concurrent Owners")
        session.add_all([*users, org])
        await session.flush()
        session.add_all(
            [
                OrganizationMemberModel(
                    organization_id=org.id, user_id=u.id, role=OrganizationRole.OWNER
                )
                for u in users
            ]
        )
        await session.commit()
        return org.id, users[0].id, users[1].id


@pytest.mark.parametrize("second_action", ["demote", "remove"])
async def test_concurrent_owner_mutations_keep_one_owner(
    postgresql_database, second_action
):
    org_id, first, second = await _two_owner_org(postgresql_database)

    async def demote(actor, target):
        async with postgresql_database.session_factory() as session:
            try:
                await change_member_role(
                    session, org_id, actor, target, OrganizationRole.ADMIN
                )
                await session.commit()
                return "committed"
            except DomainError as exc:
                await session.rollback()
                return exc.code

    async def remove(actor, target):
        async with postgresql_database.session_factory() as session:
            try:
                await remove_organization_member(session, org_id, actor, target)
                await session.commit()
                return "committed"
            except DomainError as exc:
                await session.rollback()
                return exc.code

    second_call = (
        demote(second, second) if second_action == "demote" else remove(second, second)
    )
    outcomes = await asyncio.gather(demote(first, first), second_call)
    assert sorted(outcomes) == ["LAST_OWNER_REQUIRED", "committed"]

    async with postgresql_database.session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(OrganizationMemberModel)
            .where(
                OrganizationMemberModel.organization_id == org_id,
                OrganizationMemberModel.role == OrganizationRole.OWNER,
            )
        )
    assert count == 1
