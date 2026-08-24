import pytest

from .safety import (
    DOWNGRADE_CONFIRMATION,
    TEST_DATABASE_CONFIRMATION,
    DatabaseSafetyError,
    require_downgrade_confirmation,
    validate_test_database_target,
    verify_connected_database_identity,
)

SAFE_URL = (
    "postgresql+psycopg://platform_test:local-password@db.internal:5432/platform_test"
)


def environment(**overrides: str) -> dict[str, str]:
    values = {
        "TEST_DATABASE_URL": SAFE_URL,
        "TEST_DATABASE_CONFIRM": TEST_DATABASE_CONFIRMATION,
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize("confirmation", ["", "yes", "true", "I_UNDERSTAND"])
def test_exact_opt_in_is_required_before_connection(confirmation: str) -> None:
    with pytest.raises(DatabaseSafetyError, match="confirmation"):
        validate_test_database_target(environment(TEST_DATABASE_CONFIRM=confirmation))


@pytest.mark.parametrize("database", ["platform", "prod", "production", "live"])
def test_non_test_database_names_are_rejected(database: str) -> None:
    url = f"postgresql+psycopg://platform_test:secret@db.internal:5432/{database}"
    with pytest.raises(DatabaseSafetyError, match="database name"):
        validate_test_database_target(environment(TEST_DATABASE_URL=url))


def test_dedicated_non_test_role_is_rejected() -> None:
    url = "postgresql+psycopg://platform:secret@db.internal:5432/platform_test"
    with pytest.raises(DatabaseSafetyError, match="database role"):
        validate_test_database_target(environment(TEST_DATABASE_URL=url))


@pytest.mark.parametrize("app_env", ["production", "Production", "PRODUCTION"])
def test_production_environment_is_always_rejected(app_env: str) -> None:
    with pytest.raises(DatabaseSafetyError, match="APP_ENV"):
        validate_test_database_target(environment(APP_ENV=app_env))


def test_missing_app_env_does_not_bypass_database_and_role_guards() -> None:
    target = validate_test_database_target(environment())
    assert target.database == "platform_test"
    assert target.username == "platform_test"


def test_error_never_contains_password_or_full_url() -> None:
    unsafe_url = "postgresql+psycopg://platform:very-secret@db.internal:5432/platform"
    with pytest.raises(DatabaseSafetyError) as captured:
        validate_test_database_target(environment(TEST_DATABASE_URL=unsafe_url))
    message = str(captured.value)
    assert "very-secret" not in message
    assert unsafe_url not in message


def test_downgrade_requires_independent_confirmation() -> None:
    with pytest.raises(DatabaseSafetyError, match="downgrade"):
        require_downgrade_confirmation(environment())

    require_downgrade_confirmation(
        environment(TEST_DATABASE_ALLOW_DOWNGRADE=DOWNGRADE_CONFIRMATION)
    )


class FakeResult:
    def __init__(self, row: tuple[str, str, bool]) -> None:
        self.row = row

    def one(self) -> tuple[str, str, bool]:
        return self.row


class FakeConnection:
    def __init__(self, row: tuple[str, str, bool]) -> None:
        self.row = row

    async def execute(self, _statement) -> FakeResult:
        return FakeResult(self.row)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row",
    [
        ("wrong_test", "platform_test", False),
        ("platform_test", "wrong_test", False),
        ("platform_test", "platform_test", True),
    ],
)
async def test_connected_identity_and_non_superuser_are_required(row) -> None:
    target = validate_test_database_target(environment())
    with pytest.raises(DatabaseSafetyError, match="unsafe test target"):
        await verify_connected_database_identity(FakeConnection(row), target)
