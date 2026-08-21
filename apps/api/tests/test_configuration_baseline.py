from pathlib import Path

import pytest

from platform_api.settings import Settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = REPOSITORY_ROOT / ".env.example"
COMPOSE_FILE = REPOSITORY_ROOT / "deploy" / "compose" / "docker-compose.yml"


def deployment_settings(**overrides: str) -> dict[str, str]:
    values = {
        "app_env": "production",
        "database_url": "postgresql+psycopg://app:strong-password@db.internal:5432/platform",
        "redis_url": "rediss://redis.internal:6379/0",
        "temporal_address": "temporal.internal:7233",
        "keycloak_issuer": "https://auth.example.com/realms/platform",
        "oidc_audience": "platform-api",
        "oss_public_endpoint": "https://objects.example.com",
        "oss_internal_endpoint": "http://minio.internal:9000",
        "oss_bucket": "platform-assets",
    }
    values.update(overrides)
    return values


def test_local_environment_keeps_explicit_development_defaults() -> None:
    settings = Settings(app_env="local", _env_file=None)

    assert "127.0.0.1" in settings.database_url
    assert settings.redis_url == "redis://127.0.0.1:6379/0"


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_deployment_environment_requires_explicit_external_dependencies(
    app_env: str,
) -> None:
    with pytest.raises(RuntimeError, match="database_url"):
        Settings(
            **deployment_settings(app_env=app_env, database_url=""),
            _env_file=None,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (
            "database_url",
            "postgresql+psycopg://platform:platform@127.0.0.1:5432/platform",
        ),
        ("redis_url", "redis://localhost:6379/0"),
        ("temporal_address", "127.0.0.1:7233"),
        ("keycloak_issuer", "http://localhost:8081/realms/platform"),
        ("oss_public_endpoint", "http://127.0.0.1:9000"),
    ],
)
def test_production_rejects_local_or_insecure_service_configuration(
    field: str, value: str
) -> None:
    with pytest.raises(RuntimeError) as captured:
        Settings(**deployment_settings(**{field: value}), _env_file=None)

    message = str(captured.value)
    assert field in message
    assert value not in message
    assert "strong-password" not in message


def test_production_rejects_local_default_database_credentials() -> None:
    with pytest.raises(RuntimeError, match="database_url"):
        Settings(
            **deployment_settings(
                database_url="postgresql+psycopg://platform:platform@db.internal:5432/platform"
            ),
            _env_file=None,
        )


def test_environment_example_matches_runtime_configuration_names() -> None:
    names = {
        line.split("=", 1)[0]
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    }

    assert {
        "APP_ENV",
        "APP_NAME",
        "APP_VERSION",
        "DATABASE_URL",
        "REDIS_URL",
        "TEMPORAL_ADDRESS",
        "TEMPORAL_NAMESPACE",
        "KEYCLOAK_ISSUER",
        "OIDC_AUDIENCE",
        "OSS_PUBLIC_ENDPOINT",
        "OSS_INTERNAL_ENDPOINT",
        "OSS_BUCKET",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
    } <= names
    assert "KEYCLOAK_CLIENT_ID" not in names


def test_compose_has_no_obsolete_version_and_binds_ports_to_loopback() -> None:
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    assert not compose.startswith("version:")
    assert '"127.0.0.1:5432:5432"' in compose
    assert '"127.0.0.1:6379:6379"' in compose
    assert '"127.0.0.1:9000:9000"' in compose
    assert "local-only" in compose
