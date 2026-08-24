from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncConnection

TEST_DATABASE_CONFIRMATION = "M0R05R01_TEST_DATABASE_ONLY"
DOWNGRADE_CONFIRMATION = "M0R05R01_DISPOSABLE_DATABASE_DOWNGRADE"


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


def require_downgrade_confirmation(environment: Mapping[str, str]) -> None:
    if environment.get("TEST_DATABASE_ALLOW_DOWNGRADE") != DOWNGRADE_CONFIRMATION:
        raise DatabaseSafetyError(
            "independent downgrade confirmation is missing or invalid"
        )


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
