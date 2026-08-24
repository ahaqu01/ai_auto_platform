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
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from platform_api.auth.dependencies import get_token_verifier
from platform_api.auth.identity import IdentityClaims
from platform_api.common.errors import DomainError
from platform_api.db.session import get_session
from platform_api.main import create_app

from .safety import (
    DISPOSAL_MARKER_PREFIX,
    DatabaseSafetyError,
    TestDatabaseTarget,
    assert_migrations_downgrade_safe,
    require_database_destroy_confirmation,
    require_downgrade_confirmation,
    validate_admin_database_url,
    validate_test_database_target,
    verify_connected_database_identity,
    verify_disposable_database,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "apps" / "api" / "alembic.ini"
MIGRATIONS = REPOSITORY_ROOT / "apps" / "api" / "migrations"


@dataclass(frozen=True)
class PostgresqlDatabase:
    schema: str
    engine: AsyncEngine
    session_factory: async_sessionmaker
    alembic_config: Config
    head_revisions: tuple[str, ...]

    async def upgrade(self, revision: str) -> None:
        await asyncio.to_thread(command.upgrade, self.alembic_config, revision)


@dataclass(frozen=True)
class DisposablePostgresqlDatabase(PostgresqlDatabase):
    target: TestDatabaseTarget
    disposal_marker: str

    async def downgrade(self, revision: str) -> None:
        require_downgrade_confirmation(os.environ)
        assert_migrations_downgrade_safe(sorted((MIGRATIONS / "versions").glob("*.py")))
        async with self.engine.connect() as connection:
            await verify_connected_database_identity(connection, self.target)
            await verify_disposable_database(
                connection, self.target, self.disposal_marker
            )
        await self.engine.dispose()
        await asyncio.to_thread(command.downgrade, self.alembic_config, revision)


@dataclass(frozen=True)
class PostgresqlApi:
    database: PostgresqlDatabase
    client: AsyncClient


@dataclass(frozen=True)
class FakeTokenVerifier:
    async def verify(self, token: str) -> IdentityClaims:
        identities = {
            "owner-token": IdentityClaims(
                issuer="https://auth.example.com/realms/platform",
                subject="owner-subject",
                email="owner@example.com",
                display_name="Owner",
            ),
            "outsider-token": IdentityClaims(
                issuer="https://auth.example.com/realms/platform",
                subject="outsider-subject",
                email="outsider@example.com",
                display_name="Outsider",
            ),
        }
        try:
            return identities[token]
        except KeyError as exc:
            raise DomainError("AUTHENTICATION_REQUIRED", "身份凭证无效", 401) from exc


def _test_database_target() -> TestDatabaseTarget:
    return validate_test_database_target(os.environ)


def _schema_url(url: URL, schema: str) -> URL:
    return url.update_query_dict({"options": f"-csearch_path={schema}"})


def _alembic_config(url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIGRATIONS))
    rendered = url.render_as_string(hide_password=False).replace("%", "%%")
    config.set_main_option("sqlalchemy.url", rendered)
    return config


def _heads(config: Config) -> tuple[str, ...]:
    heads = tuple(sorted(ScriptDirectory.from_config(config).get_heads()))
    assert heads
    return heads


@pytest.fixture
async def postgresql_database() -> AsyncIterator[PostgresqlDatabase]:
    target = _test_database_target()
    schema = f"test_{uuid4().hex}"
    assert schema.startswith("test_")

    admin_engine = create_async_engine(target.url, isolation_level="AUTOCOMMIT")
    test_engine: AsyncEngine | None = None
    try:
        async with admin_engine.connect() as connection:
            await verify_connected_database_identity(connection, target)
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))

        isolated_url = _schema_url(target.url, schema)
        config = _alembic_config(isolated_url)
        head_revisions = _heads(config)
        await asyncio.to_thread(command.upgrade, config, "heads")

        test_engine = create_async_engine(isolated_url, pool_pre_ping=True)
        factory = async_sessionmaker(test_engine, expire_on_commit=False)
        yield PostgresqlDatabase(
            schema=schema,
            engine=test_engine,
            session_factory=factory,
            alembic_config=config,
            head_revisions=head_revisions,
        )
    finally:
        if test_engine is not None:
            await test_engine.dispose()
        if schema.startswith("test_"):
            async with admin_engine.connect() as connection:
                await verify_connected_database_identity(connection, target)
                await connection.execute(
                    text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                )
        await admin_engine.dispose()


@pytest.fixture
async def disposable_postgresql_database() -> AsyncIterator[
    DisposablePostgresqlDatabase
]:
    base_target = _test_database_target()
    admin_url = validate_admin_database_url(os.environ)
    suffix = uuid4().hex
    database_name = f"platform_ephemeral_{suffix}_test"
    marker = f"{DISPOSAL_MARKER_PREFIX}{suffix}"
    schema = f"test_{suffix}"
    target = TestDatabaseTarget(
        url=base_target.url.set(database=database_name),
        database=database_name,
        username=base_target.username,
    )
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    test_engine: AsyncEngine | None = None
    created = False
    quote = admin_engine.dialect.identifier_preparer.quote
    quoted_database = quote(database_name)
    quoted_owner = quote(base_target.username)
    try:
        async with admin_engine.connect() as connection:
            can_create = (
                await connection.execute(
                    text(
                        "select coalesce(rolsuper or rolcreatedb, false) "
                        "from pg_roles where rolname = current_user"
                    )
                )
            ).scalar_one()
            if not can_create:
                raise DatabaseSafetyError(
                    "database admin role cannot create disposable databases"
                )
            await connection.execute(
                text(f"CREATE DATABASE {quoted_database} OWNER {quoted_owner}")
            )
            created = True
            await connection.execute(
                text(f"COMMENT ON DATABASE {quoted_database} IS '{marker}'")
            )

        bootstrap_engine = create_async_engine(target.url, isolation_level="AUTOCOMMIT")
        try:
            async with bootstrap_engine.connect() as connection:
                await verify_connected_database_identity(connection, target)
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        finally:
            await bootstrap_engine.dispose()

        isolated_url = _schema_url(target.url, schema)
        config = _alembic_config(isolated_url)
        head_revisions = _heads(config)
        await asyncio.to_thread(command.upgrade, config, "heads")
        test_engine = create_async_engine(isolated_url, pool_pre_ping=True)
        factory = async_sessionmaker(test_engine, expire_on_commit=False)
        yield DisposablePostgresqlDatabase(
            schema=schema,
            engine=test_engine,
            session_factory=factory,
            alembic_config=config,
            head_revisions=head_revisions,
            target=target,
            disposal_marker=marker,
        )
    finally:
        if test_engine is not None:
            await test_engine.dispose()
        if created:
            require_database_destroy_confirmation(os.environ)
            async with admin_engine.connect() as connection:
                row = (
                    await connection.execute(
                        text(
                            "select pg_get_userbyid(datdba), "
                            "coalesce(shobj_description(oid, 'pg_database'), '') "
                            "from pg_database where datname = :database"
                        ),
                        {"database": database_name},
                    )
                ).one()
                if row != (base_target.username, marker):
                    raise DatabaseSafetyError(
                        "refusing to destroy database without matching owner and marker"
                    )
                await connection.execute(
                    text(
                        "select pg_terminate_backend(pid) from pg_stat_activity "
                        "where datname = :database and pid <> pg_backend_pid()"
                    ),
                    {"database": database_name},
                )
                await connection.execute(text(f"DROP DATABASE {quoted_database}"))
        await admin_engine.dispose()


@pytest.fixture
async def postgresql_api(
    postgresql_database: PostgresqlDatabase,
) -> AsyncIterator[PostgresqlApi]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        async with postgresql_database.session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_token_verifier] = FakeTokenVerifier
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield PostgresqlApi(database=postgresql_database, client=client)
    finally:
        app.dependency_overrides.clear()
