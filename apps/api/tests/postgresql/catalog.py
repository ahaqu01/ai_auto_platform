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


BASE_CATALOG_ALLOWLIST = SchemaCatalog(
    tables=frozenset({"alembic_version"}),
    indexes=frozenset({"alembic_version_pkc"}),
    constraints=frozenset({"alembic_version_pkc"}),
    types=frozenset({"alembic_version", "_alembic_version"}),
    sequences=frozenset(),
    triggers=frozenset(),
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
        "select sequence_name from information_schema.sequences where sequence_schema = :schema",
        schema,
    )
    triggers = await _names(
        connection,
        "select distinct trigger_name from information_schema.triggers where trigger_schema = :schema",
        schema,
    )
    return SchemaCatalog(
        tables=tables,
        indexes=indexes,
        constraints=constraints,
        types=types,
        sequences=sequences,
        triggers=triggers,
    )
