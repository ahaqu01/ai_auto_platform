from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncConnection

TEST_DATABASE_CONFIRMATION = "M0R05R01_TEST_DATABASE_ONLY"
DOWNGRADE_CONFIRMATION = "M0R05R01_DISPOSABLE_DATABASE_DOWNGRADE"
DESTROY_CONFIRMATION = "M0R05R04_DESTROY_EPHEMERAL_DATABASE"
DISPOSAL_MARKER_PREFIX = "M0R05R04:"
_GLOBAL_DDL = re.compile(
    r"\b(?:create|alter|drop)\s+(?:database|role|user|tablespace|subscription|extension|event\s+trigger|foreign\s+data\s+wrapper|server)\b",
    re.IGNORECASE,
)
_SCHEMA_DDL = re.compile(
    r"\b(?:create|alter|drop|truncate|comment\s+on)\s+"
    r"(?:table|index|sequence|type|view|materialized\s+view|function|procedure|schema)"
    r"(?:\s+if\s+(?:not\s+)?exists)?\s+(?:[\w\"]+\.)",
    re.IGNORECASE,
)
_DATABASE_WIDE_SCHEMA_DDL = re.compile(
    r"\b(?:create|alter|drop)\s+schema\b", re.IGNORECASE
)


class DatabaseSafetyError(RuntimeError):
    """Raised before destructive test-database operations are permitted."""


@dataclass(frozen=True)
class TestDatabaseTarget:
    url: URL
    database: str
    username: str


def validate_test_database_target(environment: Mapping[str, str]) -> TestDatabaseTarget:
    if environment.get("TEST_DATABASE_CONFIRM") != TEST_DATABASE_CONFIRMATION:
        raise DatabaseSafetyError("test database confirmation is missing or invalid")

    raw_url = environment.get("TEST_DATABASE_URL", "")
    try:
        url = make_url(raw_url)
    except Exception as exc:
        raise DatabaseSafetyError("TEST_DATABASE_URL is invalid") from exc

    if url.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise DatabaseSafetyError(
            "test database must use the supported PostgreSQL driver"
        )

    database = url.database or ""
    username = url.username or ""
    if not database.endswith("_test"):
        raise DatabaseSafetyError("test database name must end with _test")
    if not username.endswith("_test"):
        raise DatabaseSafetyError("test database role must end with _test")

    if environment.get("APP_ENV", "").strip().lower() == "production":
        raise DatabaseSafetyError(
            "APP_ENV=production cannot run database integration tests"
        )

    return TestDatabaseTarget(url=url, database=database, username=username)


def validate_admin_database_url(environment: Mapping[str, str]) -> URL:
    raw_url = environment.get("TEST_DATABASE_ADMIN_URL", "")
    try:
        url = make_url(raw_url)
    except Exception as exc:
        raise DatabaseSafetyError("TEST_DATABASE_ADMIN_URL is invalid") from exc
    if url.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise DatabaseSafetyError("database admin URL must use PostgreSQL")
    if not url.database or not url.username:
        raise DatabaseSafetyError("database admin URL is incomplete")
    return url


def require_downgrade_confirmation(environment: Mapping[str, str]) -> None:
    if environment.get("TEST_DATABASE_ALLOW_DOWNGRADE") != DOWNGRADE_CONFIRMATION:
        raise DatabaseSafetyError(
            "independent downgrade confirmation is missing or invalid"
        )


def require_database_destroy_confirmation(environment: Mapping[str, str]) -> None:
    if environment.get("TEST_DATABASE_ALLOW_DESTROY") != DESTROY_CONFIRMATION:
        raise DatabaseSafetyError(
            "independent database destroy confirmation is missing or invalid"
        )


def assert_migrations_downgrade_safe(paths: Iterable[Path]) -> None:
    for path in paths:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "execute"
                    and (
                        not node.args
                        or not isinstance(node.args[0], ast.Constant)
                        or not isinstance(node.args[0].value, str)
                    )
                ):
                    raise DatabaseSafetyError(
                        f"unsafe migration DDL uses dynamic execute in {path.name}"
                    )
                for keyword in node.keywords:
                    if keyword.arg == "schema" and not (
                        isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is None
                    ):
                        raise DatabaseSafetyError(
                            f"unsafe migration DDL uses schema= in {path.name}"
                        )
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                statement = node.value
                if (
                    _GLOBAL_DDL.search(statement)
                    or _SCHEMA_DDL.search(statement)
                    or _DATABASE_WIDE_SCHEMA_DDL.search(statement)
                ):
                    raise DatabaseSafetyError(f"unsafe migration DDL in {path.name}")


async def verify_connected_database_identity(
    connection: AsyncConnection, target: TestDatabaseTarget
) -> None:
    row = (
        await connection.execute(
            text(
                "select current_database(), current_user, "
                "coalesce((select rolsuper from pg_roles where rolname = current_user), true)"
            )
        )
    ).one()
    current_database, current_user, is_superuser = row
    invalid: list[str] = []
    if current_database != target.database:
        invalid.append("database identity")
    if current_user != target.username:
        invalid.append("database role identity")
    if is_superuser:
        invalid.append("database role privileges")
    if invalid:
        raise DatabaseSafetyError("unsafe test target: " + ", ".join(invalid))


async def verify_disposable_database(
    connection: AsyncConnection,
    target: TestDatabaseTarget,
    marker: str,
) -> None:
    if not marker.startswith(DISPOSAL_MARKER_PREFIX):
        raise DatabaseSafetyError("invalid disposal marker")
    row = (
        await connection.execute(
            text(
                "select pg_get_userbyid(d.datdba), "
                "coalesce(shobj_description(d.oid, 'pg_database'), ''), "
                "(select count(*) from pg_stat_activity "
                "where datname = current_database() and pid <> pg_backend_pid()) "
                "from pg_database d where d.datname = current_database()"
            )
        )
    ).one()
    owner, actual_marker, other_connections = row
    invalid: list[str] = []
    if owner != target.username:
        invalid.append("database owner")
    if actual_marker != marker:
        invalid.append("disposal marker")
    if other_connections != 0:
        invalid.append("shared connections")
    if invalid:
        raise DatabaseSafetyError("unsafe disposable database: " + ", ".join(invalid))
