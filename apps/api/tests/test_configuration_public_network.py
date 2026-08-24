from collections.abc import Iterable

import pytest
from pydantic import ValidationError

from platform_api.auth.verifier import SafePyJWKClient
from platform_api.common.public_network import (
    PublicNetworkPolicyError,
    validate_public_url,
    validate_redirect_target,
)
from platform_api.settings import Settings


def deployment_settings(**overrides: str) -> dict[str, str]:
    values = {
        "app_env": "production",
        "database_url": "postgresql+psycopg://app:strong-password@db.internal:5432/platform?sslmode=verify-full",
        "redis_url": "rediss://redis.internal:6379/0",
        "temporal_address": "temporal.internal:7233",
        "keycloak_issuer": "https://auth.example.com/realms/platform",
        "oidc_audience": "platform-api",
        "oss_public_endpoint": "https://objects.example.com",
        "oss_internal_endpoint": "http://10.20.30.40:9000",
        "oss_bucket": "platform-assets",
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.20.30.40",
        "169.254.169.254",
        "0.0.0.0",
        "192.0.2.10",
        "224.0.0.1",
        "100.100.100.200",
        "::1",
        "fe80::1",
    ],
)
@pytest.mark.parametrize("field", ["keycloak_issuer", "oss_public_endpoint"])
def test_public_endpoints_reject_non_global_ip_literals(
    field: str, address: str
) -> None:
    host = f"[{address}]" if ":" in address else address
    value = (
        f"https://{host}/realms/platform"
        if field == "keycloak_issuer"
        else f"https://{host}"
    )

    with pytest.raises(RuntimeError) as captured:
        Settings(**deployment_settings(**{field: value}), _env_file=None)

    assert field in str(captured.value)
    assert value not in str(captured.value)


@pytest.mark.parametrize(
    "hostname",
    ["metadata", "metadata.google.internal", "metadata.aliyun.com"],
)
def test_public_endpoints_reject_known_metadata_hostnames(hostname: str) -> None:
    with pytest.raises(RuntimeError, match="oss_public_endpoint"):
        Settings(
            **deployment_settings(
                oss_public_endpoint=f"https://{hostname}",
            ),
            _env_file=None,
        )


def test_internal_oss_endpoint_accepts_private_network_address() -> None:
    settings = Settings(**deployment_settings(), _env_file=None)
    assert settings.oss_internal_endpoint == "http://10.20.30.40:9000"


def test_settings_are_frozen_after_construction() -> None:
    settings = Settings(app_env="local", _env_file=None)

    with pytest.raises(ValidationError):
        settings.app_name = "changed"


def resolver_returning(*addresses: str):
    def resolve(_hostname: str, _port: int) -> Iterable[str]:
        return addresses

    return resolve


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.5", "169.254.169.254", "0.0.0.0", "192.0.2.5"],
)
def test_runtime_policy_rejects_dns_answers_in_sensitive_networks(
    address: str,
) -> None:
    with pytest.raises(PublicNetworkPolicyError):
        validate_public_url(
            "https://auth.example.com/realms/platform",
            resolver=resolver_returning(address),
        )


def test_runtime_policy_rejects_empty_dns_answer() -> None:
    with pytest.raises(PublicNetworkPolicyError):
        validate_public_url(
            "https://auth.example.com/realms/platform",
            resolver=resolver_returning(),
        )


def test_runtime_policy_accepts_only_global_dns_answers() -> None:
    validate_public_url(
        "https://auth.example.com/realms/platform",
        resolver=resolver_returning(
            "93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"
        ),
    )


def test_runtime_policy_rejects_redirect_to_sensitive_address() -> None:
    with pytest.raises(PublicNetworkPolicyError):
        validate_redirect_target(
            "https://auth.example.com/realms/platform/protocol/openid-connect/certs",
            "https://169.254.169.254/latest/meta-data",
            resolver=resolver_returning("169.254.169.254"),
        )


def test_runtime_policy_accepts_relative_redirect_to_public_address() -> None:
    target = validate_redirect_target(
        "https://auth.example.com/realms/platform/protocol/openid-connect/certs",
        "/keys/current",
        resolver=resolver_returning("93.184.216.34"),
    )
    assert target == "https://auth.example.com/keys/current"


def test_oidc_default_jwks_client_uses_public_network_policy() -> None:
    from platform_api.auth.verifier import OidcTokenVerifier

    verifier = OidcTokenVerifier(
        "https://auth.example.com/realms/platform", "platform-api"
    )
    assert isinstance(verifier.jwks_client, SafePyJWKClient)
