import pytest
from sqlalchemy import text

from .catalog import BASE_CATALOG_ALLOWLIST, collect_schema_catalog

pytestmark = [pytest.mark.asyncio, pytest.mark.postgresql]


async def database_revisions(postgresql_database) -> frozenset[str]:
    async with postgresql_database.engine.connect() as connection:
        result = await connection.execute(
            text("select version_num from alembic_version")
        )
        return frozenset(result.scalars())


async def test_database_contains_every_script_head(postgresql_database) -> None:
    assert postgresql_database.head_revisions
    assert await database_revisions(postgresql_database) == frozenset(
        postgresql_database.head_revisions
    )


async def test_base_catalog_matches_explicit_allowlist_before_all_heads_roundtrip(
    disposable_postgresql_database,
) -> None:
    postgresql_database = disposable_postgresql_database
    await postgresql_database.downgrade("base")
    async with postgresql_database.engine.connect() as connection:
        inventory = await collect_schema_catalog(connection, postgresql_database.schema)

    assert inventory == BASE_CATALOG_ALLOWLIST

    await postgresql_database.upgrade("heads")
    assert await database_revisions(postgresql_database) == frozenset(
        postgresql_database.head_revisions
    )
