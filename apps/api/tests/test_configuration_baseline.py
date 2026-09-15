from pathlib import Path

import pytest

from platform_api.settings import Settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = REPOSITORY_ROOT / ".env.example"
COMPOSE_FILE = REPOSITORY_ROOT / "deploy" / "compose" / "docker-compose.yml"


def deployment_settings(**overrides: str) -> dict[str, str]:
    values = {
        "app_env": "production",
        "database_url": "postgresql+psycopg://app:strong-password@db.internal:5432/platform?sslmode=verify-full",
        "redis_url": "rediss://redis.internal:6379/0",
        "temporal_address": "temporal.internal:7233",
        "keycloak_issuer": "https://auth.example.com/realms/platform",
        "oidc_audience": "platform-api",
        "bff_client_secret": "deployment-bff-secret",
        "bff_public_origin": "https://platform.example.com",
        "bff_callback_url": "https://platform.example.com/auth/callback",
        "oss_public_endpoint": "https://objects.example.com",
        "oss_internal_endpoint": "http://minio.internal:9000",
        "oss_bucket": "platform-assets",
        "oss_provider": "minio",
        "oss_region": "us-east-1",
        "oss_access_key_id": "test-access-id",
        "oss_access_key_secret": "test-access-secret",
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
        ("bff_public_origin", "http://localhost:8080"),
        ("bff_callback_url", "http://localhost:8080/auth/callback"),
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


@pytest.mark.parametrize(
    "field",
    ["bff_client_secret", "bff_public_origin", "bff_callback_url"],
)
def test_deployment_requires_explicit_bff_configuration(field: str) -> None:
    with pytest.raises(RuntimeError, match=field):
        Settings(**deployment_settings(**{field: ""}), _env_file=None)


@pytest.mark.parametrize(
    "callback_url",
    [
        "https://other.example.com/auth/callback",
        "https://platform.example.com/wrong/callback",
        "https://platform.example.com/auth/callback?code=leak",
    ],
)
def test_deployment_rejects_invalid_bff_callback(callback_url: str) -> None:
    with pytest.raises(RuntimeError, match="bff_callback_url"):
        Settings(**deployment_settings(bff_callback_url=callback_url), _env_file=None)


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
        "BFF_CLIENT_ID",
        "BFF_CLIENT_SECRET",
        "BFF_PUBLIC_ORIGIN",
        "BFF_CALLBACK_URL",
        "OSS_PROVIDER",
        "OSS_REGION",
        "OSS_ACCESS_KEY_ID",
        "OSS_ACCESS_KEY_SECRET",
        "OSS_SESSION_TOKEN",
        "OSS_PUBLIC_ENDPOINT",
        "OSS_INTERNAL_ENDPOINT",
        "OSS_BUCKET",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "ALLOW_INSECURE_PRIVATE_SERVICE_TRANSPORT",
    } <= names
    assert "KEYCLOAK_CLIENT_ID" not in names


def test_compose_has_no_obsolete_version_and_binds_ports_to_loopback() -> None:
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    assert not compose.startswith("version:")
    assert '"127.0.0.1:5432:5432"' in compose
    assert '"127.0.0.1:6379:6379"' in compose
    assert '"127.0.0.1:9000:9000"' in compose
    assert "local-only" in compose


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (
            "database_url",
            "postgresql+psycopg://app:strong-password@db.internal:5432/platform",
        ),
        ("redis_url", "redis://redis.internal:6379/0"),
    ],
)
def test_production_requires_verified_service_tls(field: str, value: str) -> None:
    with pytest.raises(RuntimeError, match=field):
        Settings(**deployment_settings(**{field: value}), _env_file=None)


def test_explicit_private_transport_exception_is_limited_to_internal_hosts() -> None:
    settings = Settings(
        **deployment_settings(
            database_url=(
                "postgresql+psycopg://app:strong-password@db.internal:5432/platform"
            ),
            redis_url="redis://redis.internal:6379/0",
            allow_insecure_private_service_transport=True,
        ),
        _env_file=None,
    )
    assert settings.allow_insecure_private_service_transport is True

    with pytest.raises(RuntimeError, match="database_url"):
        Settings(
            **deployment_settings(
                database_url=(
                    "postgresql+psycopg://app:strong-password@db.example.com:5432/"
                    "platform"
                ),
                allow_insecure_private_service_transport=True,
            ),
            _env_file=None,
        )


def test_keycloak_issuer_accepts_safe_context_prefix() -> None:
    settings = Settings(
        **deployment_settings(
            keycloak_issuer="https://auth.example.com/auth/realms/platform"
        ),
        _env_file=None,
    )
    assert settings.keycloak_issuer.endswith("/auth/realms/platform")


@pytest.mark.parametrize(
    "issuer",
    [
        "https://user@auth.example.com/auth/realms/platform",
        "https://auth.example.com/auth/realms/platform?tenant=x",
        "https://auth.example.com/auth/realms/platform#fragment",
        "https://auth.example.com/auth/not-realms/platform",
    ],
)
def test_keycloak_context_prefix_does_not_bypass_url_guards(issuer: str) -> None:
    with pytest.raises(RuntimeError, match="keycloak_issuer"):
        Settings(
            **deployment_settings(keycloak_issuer=issuer),
            _env_file=None,
        )
