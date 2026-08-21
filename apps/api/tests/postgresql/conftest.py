from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "apps" / "api" / "alembic.ini"
MIGRATIONS = REPOSITORY_ROOT / "apps" / "api" / "migrations"


@dataclass(frozen=True)
class PostgresqlDatabase:
    schema: str
    engine: AsyncEngine
    session_factory: async_sessionmaker
    alembic_config: Config
    head_revision: str


def _test_database_url() -> URL:
    raw_url = os.getenv("TEST_DATABASE_URL")
    if not raw_url:
        raise pytest.UsageError(
            "PostgreSQL integration tests require an explicit TEST_DATABASE_URL"
        )
    url = make_url(raw_url)
    if url.get_backend_name() != "postgresql":
        raise pytest.UsageError("TEST_DATABASE_URL must use PostgreSQL")
    if (
        os.getenv("APP_ENV") == "production"
        or "production" in (url.database or "").lower()
    ):
        raise pytest.UsageError("TEST_DATABASE_URL must not target production")
    return url


def _schema_url(url: URL, schema: str) -> URL:
    return url.update_query_dict({"options": f"-csearch_path={schema}"})


def _alembic_config(url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIGRATIONS))
    rendered = url.render_as_string(hide_password=False).replace("%", "%%")
    config.set_main_option("sqlalchemy.url", rendered)
    return config


@pytest.fixture
async def postgresql_database() -> AsyncIterator[PostgresqlDatabase]:
    base_url = _test_database_url()
    schema = f"test_{uuid4().hex}"
    assert schema.startswith("test_")

    admin_engine = create_async_engine(base_url, isolation_level="AUTOCOMMIT")
    test_engine: AsyncEngine | None = None
    try:
        async with admin_engine.connect() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))

        isolated_url = _schema_url(base_url, schema)
        config = _alembic_config(isolated_url)
        await asyncio.to_thread(command.upgrade, config, "head")

        test_engine = create_async_engine(isolated_url, pool_pre_ping=True)
        factory = async_sessionmaker(test_engine, expire_on_commit=False)
        head_revision = ScriptDirectory.from_config(config).get_current_head()
        assert head_revision is not None
        yield PostgresqlDatabase(
            schema=schema,
            engine=test_engine,
            session_factory=factory,
            alembic_config=config,
            head_revision=head_revision,
        )
    finally:
        if test_engine is not None:
            await test_engine.dispose()
        if schema.startswith("test_"):
            async with admin_engine.connect() as connection:
                await connection.execute(
                    text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                )
        await admin_engine.dispose()
