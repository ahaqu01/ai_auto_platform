import pytest

from platform_api.settings import Settings


def valid_deployment(**overrides: str) -> dict[str, str]:
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


@pytest.mark.parametrize(
    "value",
    [
        "sqlite:///tmp/platform.db",
        "postgresql://app:password@db.internal:5432/platform",
        "postgresql+psycopg://db.internal:5432/platform",
        "postgresql+psycopg://app@db.internal:5432/platform",
        "postgresql+psycopg://app:password@:5432/platform",
        "postgresql+psycopg://app:password@db.internal/platform",
        "postgresql+psycopg://app:password@db.internal:5432",
        "postgresql+psycopg://app:password@db.internal:notaport/platform",
    ],
)
def test_database_url_requires_supported_complete_structure(value: str) -> None:
    with pytest.raises(RuntimeError, match="database_url"):
        Settings(**valid_deployment(database_url=value), _env_file=None)


@pytest.mark.parametrize(
    "value",
    [
        "garbage",
        "http://redis.internal:6379/0",
        "redis:///0",
        "redis://redis.internal/0",
        "redis://redis.internal:notaport/0",
        "redis://redis.internal:6379/not-a-number",
        "redis://redis.internal:6379/0/extra",
    ],
)
def test_redis_url_requires_supported_complete_structure(value: str) -> None:
    with pytest.raises(RuntimeError, match="redis_url"):
        Settings(**valid_deployment(redis_url=value), _env_file=None)


@pytest.mark.parametrize(
    "value",
    [
        "garbage",
        "http://temporal.internal:7233",
        "temporal.internal",
        "temporal.internal:notaport",
        "user@temporal.internal:7233",
        "temporal.internal:7233/path",
        "temporal.internal:7233?query=yes",
    ],
)
def test_temporal_address_is_plain_host_and_port(value: str) -> None:
    with pytest.raises(RuntimeError, match="temporal_address"):
        Settings(**valid_deployment(temporal_address=value), _env_file=None)


@pytest.mark.parametrize(
    "value",
    [
        "https:///realms/platform",
        "https://auth.example.com",
        "https://auth.example.com/not-realms/platform",
        "https://user@auth.example.com/realms/platform",
        "https://auth.example.com/realms/platform?query=yes",
        "https://auth.example.com/realms/platform#fragment",
    ],
)
def test_keycloak_issuer_has_expected_https_structure(value: str) -> None:
    with pytest.raises(RuntimeError, match="keycloak_issuer"):
        Settings(**valid_deployment(keycloak_issuer=value), _env_file=None)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("oss_public_endpoint", "http://objects.example.com"),
        ("oss_public_endpoint", "https:///objects"),
        ("oss_public_endpoint", "https://objects.example.com/bucket"),
        ("oss_internal_endpoint", "ftp://minio.internal:9000"),
        ("oss_internal_endpoint", "http:///minio"),
        ("oss_internal_endpoint", "http://user@minio.internal:9000"),
        ("oss_internal_endpoint", "http://minio.internal:9000/path"),
    ],
)
def test_oss_endpoints_have_supported_endpoint_structure(
    field: str, value: str
) -> None:
    with pytest.raises(RuntimeError) as captured:
        Settings(**valid_deployment(**{field: value}), _env_file=None)
    assert field in str(captured.value)
    assert value not in str(captured.value)


def test_local_environment_remains_compatible_with_incomplete_optional_services() -> (
    None
):
    settings = Settings(app_env="local", temporal_address="garbage", _env_file=None)
    assert settings.temporal_address == "garbage"
