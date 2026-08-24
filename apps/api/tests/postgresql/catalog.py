from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass(frozen=True)
class SchemaCatalog:
    tables: frozenset[str]
    indexes: frozenset[str]
    constraints: frozenset[str]
    types: frozenset[str]
    sequences: frozenset[str]
    triggers: frozenset[str]
    views: frozenset[str]
    materialized_views: frozenset[str]
    routines: frozenset[str]
    policies: frozenset[str]
    domains: frozenset[str]
    collations: frozenset[str]
    grants: frozenset[str]


BASE_CATALOG_ALLOWLIST = SchemaCatalog(
    tables=frozenset({"alembic_version"}),
    indexes=frozenset({"alembic_version_pkc"}),
    constraints=frozenset({"alembic_version_pkc"}),
    types=frozenset({"alembic_version", "_alembic_version"}),
    sequences=frozenset(),
    triggers=frozenset(),
    views=frozenset(),
    materialized_views=frozenset(),
    routines=frozenset(),
    policies=frozenset(),
    domains=frozenset(),
    collations=frozenset(),
    grants=frozenset(),
)


async def _names(
    connection: AsyncConnection,
    statement: str,
    schema: str,
) -> frozenset[str]:
    result = await connection.execute(text(statement), {"schema": schema})
    return frozenset(result.scalars())


async def collect_schema_catalog(
    connection: AsyncConnection,
    schema: str,
) -> SchemaCatalog:
    if not schema.startswith("test_"):
        raise ValueError("catalog inspection requires an isolated test schema")

    tables = await _names(
        connection,
        """
        select table_name
        from information_schema.tables
        where table_schema = :schema and table_type = 'BASE TABLE'
        """,
        schema,
    )
    indexes = await _names(
        connection,
        "select indexname from pg_indexes where schemaname = :schema",
        schema,
    )
    constraints = await _names(
        connection,
        """
        select c.conname
        from pg_constraint c
        join pg_namespace n on n.oid = c.connamespace
        where n.nspname = :schema
        """,
        schema,
    )
    types = await _names(
        connection,
        """
        select t.typname
        from pg_type t
        join pg_namespace n on n.oid = t.typnamespace
        where n.nspname = :schema
        """,
        schema,
    )
    sequences = await _names(
        connection,
        """
        select sequence_name
        from information_schema.sequences
        where sequence_schema = :schema
        """,
        schema,
    )
    triggers = await _names(
        connection,
        """
        select distinct trigger_name
        from information_schema.triggers
        where trigger_schema = :schema
        """,
        schema,
    )
    views = await _names(
        connection,
        """
        select table_name
        from information_schema.views
        where table_schema = :schema
        """,
        schema,
    )
    materialized_views = await _names(
        connection,
        """
        select matviewname
        from pg_matviews
        where schemaname = :schema
        """,
        schema,
    )
    routines = await _names(
        connection,
        """
        select p.proname || ':' || p.prokind::text
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = :schema
        """,
        schema,
    )
    policies = await _names(
        connection,
        """
        select c.relname || ':' || p.polname
        from pg_policy p
        join pg_class c on c.oid = p.polrelid
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = :schema
        """,
        schema,
    )
    domains = await _names(
        connection,
        """
        select t.typname
        from pg_type t
        join pg_namespace n on n.oid = t.typnamespace
        where n.nspname = :schema and t.typtype = 'd'
        """,
        schema,
    )
    collations = await _names(
        connection,
        """
        select c.collname
        from pg_collation c
        join pg_namespace n on n.oid = c.collnamespace
        where n.nspname = :schema
        """,
        schema,
    )
    grants = await _names(
        connection,
        """
        select c.relname || ':' ||
               case when acl.grantee = 0 then 'PUBLIC'
                    else pg_get_userbyid(acl.grantee)
               end || ':' || acl.privilege_type
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        cross join lateral aclexplode(c.relacl) acl
        where n.nspname = :schema
        """,
        schema,
    )
    return SchemaCatalog(
        tables=tables,
        indexes=indexes,
        constraints=constraints,
        types=types,
        sequences=sequences,
        triggers=triggers,
        views=views,
        materialized_views=materialized_views,
        routines=routines,
        policies=policies,
        domains=domains,
        collations=collations,
        grants=grants,
    )
