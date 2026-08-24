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


async def test_catalog_detects_extended_residual_objects(
    disposable_postgresql_database,
) -> None:
    database = disposable_postgresql_database
    await database.downgrade("base")
    schema = database.schema
    async with database.engine.begin() as connection:
        await connection.execute(
            text(f'CREATE VIEW "{schema}".residual_view AS SELECT 1 AS id')
        )
        await connection.execute(
            text(
                f'CREATE MATERIALIZED VIEW "{schema}".residual_materialized_view '
                "AS SELECT 1 AS id"
            )
        )
        await connection.execute(
            text(
                f'CREATE FUNCTION "{schema}".residual_function() RETURNS integer '
                "LANGUAGE SQL AS 'SELECT 1'"
            )
        )
        await connection.execute(
            text(f'CREATE TABLE "{schema}".policy_target (id integer)')
        )
        await connection.execute(
            text(
                f'CREATE POLICY residual_policy ON "{schema}".policy_target '
                "USING (true)"
            )
        )
        await connection.execute(
            text(f'CREATE DOMAIN "{schema}".residual_domain AS text')
        )
        await connection.execute(
            text(f'CREATE COLLATION "{schema}".residual_collation FROM "C"')
        )
        await connection.execute(
            text(f'GRANT SELECT ON "{schema}".alembic_version TO PUBLIC')
        )
        inventory = await collect_schema_catalog(connection, schema)

    assert "residual_view" in inventory.views
    assert "residual_materialized_view" in inventory.materialized_views
    assert "residual_function:f" in inventory.routines
    assert "policy_target:residual_policy" in inventory.policies
    assert "residual_domain" in inventory.domains
    assert "residual_collation" in inventory.collations
    assert "alembic_version:PUBLIC:SELECT" in inventory.grants
