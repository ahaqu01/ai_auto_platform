from __future__ import annotations

from functools import lru_cache
from ipaddress import ip_address
from typing import Literal
from urllib.parse import ParseResult, parse_qs, urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

from platform_api.common.public_network import is_public_hostname_candidate

DEPLOYMENT_ENVIRONMENTS = {"staging", "production"}
LOCAL_HOSTNAMES = {"localhost", "localhost.localdomain"}


def _parse_url(value: str) -> ParseResult | None:
    try:
        parsed = urlparse(value)
        _ = parsed.port
    except ValueError:
        return None
    return parsed


def _parse_address(value: str) -> ParseResult | None:
    if "://" in value:
        return None
    try:
        parsed = urlparse(f"//{value}")
        _ = parsed.port
    except ValueError:
        return None
    return parsed


def _hostname(value: str) -> str | None:
    try:
        parsed = urlparse(value if "://" in value else f"//{value}")
        return parsed.hostname
    except ValueError:
        return None


def _is_local_host(value: str) -> bool:
    hostname = _hostname(value)
    if not hostname:
        return False
    normalized = hostname.rstrip(".").lower()
    if normalized in LOCAL_HOSTNAMES or normalized.endswith(".localhost"):
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def _is_private_service_endpoint(value: str) -> bool:
    hostname = _hostname(value)
    if not hostname:
        return False
    normalized = hostname.rstrip(".").lower()
    if normalized.endswith(".internal"):
        return True
    try:
        address = ip_address(normalized)
        return address.is_private and not address.is_loopback
    except ValueError:
        return False


def _is_public_endpoint(value: str) -> bool:
    hostname = _hostname(value)
    return bool(hostname and is_public_hostname_candidate(hostname))


def _valid_database_url(value: str) -> bool:
    parsed = _parse_url(value)
    if parsed is None:
        return False
    path_parts = [part for part in parsed.path.split("/") if part]
    return (
        parsed.scheme.lower() == "postgresql+psycopg"
        and bool(parsed.hostname)
        and bool(parsed.username)
        and bool(parsed.password)
        and parsed.port is not None
        and len(path_parts) == 1
        and not parsed.params
        and not parsed.fragment
    )


def _database_uses_verified_tls(value: str) -> bool:
    parsed = _parse_url(value)
    if parsed is None:
        return False
    query = parse_qs(parsed.query, keep_blank_values=True)
    return query.get("sslmode") == ["verify-full"]


def _valid_redis_url(value: str) -> bool:
    parsed = _parse_url(value)
    if parsed is None:
        return False
    database_number = parsed.path.removeprefix("/")
    return (
        parsed.scheme.lower() in {"redis", "rediss"}
        and bool(parsed.hostname)
        and parsed.port is not None
        and bool(database_number)
        and database_number.isdigit()
        and "/" not in database_number
        and not parsed.params
        and not parsed.fragment
    )


def _valid_temporal_address(value: str) -> bool:
    parsed = _parse_address(value)
    return bool(
        parsed
        and parsed.hostname
        and parsed.port is not None
        and parsed.username is None
        and parsed.password is None
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
    )


def _valid_keycloak_issuer(value: str) -> bool:
    parsed = _parse_url(value)
    if parsed is None:
        return False
    path_parts = [part for part in parsed.path.split("/") if part]
    return (
        parsed.scheme.lower() == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and len(path_parts) >= 2
        and path_parts[-2] == "realms"
        and bool(path_parts[-1])
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )


def _valid_endpoint(value: str, *, allowed_schemes: set[str]) -> bool:
    parsed = _parse_url(value)
    return bool(
        parsed
        and parsed.scheme.lower() in allowed_schemes
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    app_env: Literal["local", "test", "staging", "production"] = "local"
    app_name: str = "ai-auto-platform"
    app_version: str = "0.1.0"
    database_url: str = "postgresql+psycopg://platform:platform@127.0.0.1:5432/platform"
    redis_url: str | None = "redis://127.0.0.1:6379/0"
    temporal_address: str | None = None
    temporal_namespace: str = "default"
    keycloak_issuer: str | None = None
    oidc_audience: str | None = None
    oss_public_endpoint: str | None = None
    oss_internal_endpoint: str | None = None
    oss_bucket: str | None = None
    otel_exporter_otlp_endpoint: str | None = None
    allow_insecure_private_service_transport: bool = False

    def model_post_init(self, __context: object, /) -> None:
        self.validate_deployment()

    def validate_deployment(self) -> None:
        if self.app_env not in DEPLOYMENT_ENVIRONMENTS:
            return

        required = {
            "database_url": self.database_url,
            "redis_url": self.redis_url,
            "temporal_address": self.temporal_address,
            "keycloak_issuer": self.keycloak_issuer,
            "oidc_audience": self.oidc_audience,
            "oss_public_endpoint": self.oss_public_endpoint,
            "oss_internal_endpoint": self.oss_internal_endpoint,
            "oss_bucket": self.oss_bucket,
        }
        invalid = {
            name for name, value in required.items() if not value or not value.strip()
        }

        address_fields = {
            "database_url": self.database_url,
            "redis_url": self.redis_url,
            "temporal_address": self.temporal_address,
            "keycloak_issuer": self.keycloak_issuer,
            "oss_public_endpoint": self.oss_public_endpoint,
            "oss_internal_endpoint": self.oss_internal_endpoint,
        }
        invalid.update(
            name
            for name, value in address_fields.items()
            if value and _is_local_host(value)
        )

        public_fields = {
            "keycloak_issuer": self.keycloak_issuer,
            "oss_public_endpoint": self.oss_public_endpoint,
        }
        invalid.update(
            name
            for name, value in public_fields.items()
            if value and not _is_public_endpoint(value)
        )

        structure_checks = {
            "database_url": _valid_database_url(self.database_url),
            "redis_url": bool(self.redis_url and _valid_redis_url(self.redis_url)),
            "temporal_address": bool(
                self.temporal_address and _valid_temporal_address(self.temporal_address)
            ),
            "keycloak_issuer": bool(
                self.keycloak_issuer and _valid_keycloak_issuer(self.keycloak_issuer)
            ),
            "oss_public_endpoint": bool(
                self.oss_public_endpoint
                and _valid_endpoint(self.oss_public_endpoint, allowed_schemes={"https"})
            ),
            "oss_internal_endpoint": bool(
                self.oss_internal_endpoint
                and _valid_endpoint(
                    self.oss_internal_endpoint, allowed_schemes={"http", "https"}
                )
            ),
        }
        invalid.update(
            name for name, is_valid in structure_checks.items() if not is_valid
        )

        database_tls_exception = (
            self.allow_insecure_private_service_transport
            and _is_private_service_endpoint(self.database_url)
        )
        if (
            not _database_uses_verified_tls(self.database_url)
            and not database_tls_exception
        ):
            invalid.add("database_url")

        redis_tls_exception = bool(
            self.redis_url
            and self.allow_insecure_private_service_transport
            and _is_private_service_endpoint(self.redis_url)
        )
        if (
            self.redis_url
            and not self.redis_url.lower().startswith("rediss://")
            and not redis_tls_exception
        ):
            invalid.add("redis_url")

        database = _parse_url(self.database_url)
        if (
            database
            and database.username == "platform"
            and database.password == "platform"
        ):
            invalid.add("database_url")

        if invalid:
            names = ", ".join(sorted(invalid))
            raise RuntimeError(f"Invalid deployment settings: {names}")

    def validate_production(self) -> None:
        """Backward-compatible entry point for callers using the old name."""
        self.validate_deployment()


@lru_cache
def get_settings() -> Settings:
    return Settings()
