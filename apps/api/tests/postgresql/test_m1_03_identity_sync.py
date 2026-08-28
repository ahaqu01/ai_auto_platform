import asyncio

import pytest
from sqlalchemy import func, select, text

from platform_api.auth.dependencies import _synchronize_user
from platform_api.auth.identity import IdentityClaims
from platform_api.db.models import UserModel

pytestmark = [pytest.mark.asyncio, pytest.mark.postgresql]


async def test_email_is_not_unique_and_identity_key_is_unique(
    postgresql_database,
) -> None:
    async with postgresql_database.engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    """
                    select conname, array_agg(att.attname order by key_position)
                    from pg_constraint con
                    join lateral unnest(con.conkey)
                        with ordinality as keys(attnum, key_position) on true
                    join pg_attribute att
                      on att.attrelid = con.conrelid
                     and att.attnum = keys.attnum
                    where con.conrelid = 'users'::regclass
                      and con.contype = 'u'
                    group by conname
                    """
                )
            )
        ).all()

    constraints = {name: tuple(columns) for name, columns in rows}
    assert "uq_users_email" not in constraints
    assert constraints["uq_users_external_identity"] == (
        "external_issuer",
        "external_subject",
    )


async def test_same_email_for_different_subjects_creates_distinct_users(
    postgresql_database,
) -> None:
    identities = [
        IdentityClaims(
            issuer="https://auth.example.com/realms/platform",
            subject=f"same-email-subject-{index}",
            email="shared@example.com",
            display_name=f"Shared {index}",
        )
        for index in range(2)
    ]

    async def synchronize(identity: IdentityClaims):
        async with postgresql_database.session_factory() as session:
            user = await _synchronize_user(session, identity)
            await session.commit()
            return user

    users = await asyncio.gather(*(synchronize(identity) for identity in identities))

    assert users[0].id != users[1].id
    async with postgresql_database.session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(UserModel)
            .where(UserModel.email == "shared@example.com")
        )
    assert count == 2


async def test_twenty_concurrent_first_logins_create_one_identity(
    postgresql_database,
) -> None:
    identity = IdentityClaims(
        issuer="https://auth.example.com/realms/platform",
        subject="concurrent-first-login",
        email="concurrent@example.com",
        display_name="Concurrent User",
    )

    async def synchronize():
        async with postgresql_database.session_factory() as session:
            user = await _synchronize_user(session, identity)
            await session.commit()
            return user

    users = await asyncio.gather(*(synchronize() for _ in range(20)))

    assert len({user.id for user in users}) == 1
    async with postgresql_database.session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(UserModel)
            .where(
                UserModel.external_issuer == identity.issuer,
                UserModel.external_subject == identity.subject,
            )
        )
    assert count == 1


async def test_existing_identity_updates_only_non_empty_profile_fields(
    postgresql_database,
) -> None:
    initial = IdentityClaims(
        issuer="https://auth.example.com/realms/platform",
        subject="profile-update",
        email="before@example.com",
        display_name="Before",
    )
    updated = IdentityClaims(
        issuer=initial.issuer,
        subject=initial.subject,
        email="after@example.com",
        display_name="After",
    )
    missing = IdentityClaims(
        issuer=initial.issuer,
        subject=initial.subject,
        email=None,
        display_name="",
    )

    async with postgresql_database.session_factory() as session:
        created = await _synchronize_user(session, initial)
        created_id = created.id
        await session.commit()
    async with postgresql_database.session_factory() as session:
        changed = await _synchronize_user(session, updated)
        await session.commit()
    async with postgresql_database.session_factory() as session:
        unchanged = await _synchronize_user(session, missing)
        await session.commit()

    assert changed.id == created_id
    assert unchanged.id == created_id
    assert unchanged.email == "after@example.com"
    assert unchanged.display_name == "After"


async def test_identity_sync_participates_in_caller_transaction(
    postgresql_database,
) -> None:
    identity = IdentityClaims(
        issuer="https://auth.example.com/realms/platform",
        subject="rolled-back-identity",
        email="rollback@example.com",
        display_name="Rollback User",
    )

    async with postgresql_database.session_factory() as session:
        created = await _synchronize_user(session, identity)
        created_id = created.id
        await session.rollback()

    async with postgresql_database.session_factory() as session:
        persisted = await session.get(UserModel, created_id)

    assert persisted is None
