from __future__ import annotations

from functools import lru_cache
from ipaddress import ip_address
from typing import Literal
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

DEPLOYMENT_ENVIRONMENTS = {"staging", "production"}
LOCAL_HOSTNAMES = {"localhost", "localhost.localdomain"}


def _hostname(value: str) -> str | None:
    parsed = urlparse(value if "://" in value else f"//{value}")
    return parsed.hostname


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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
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

        https_fields = {
            "keycloak_issuer": self.keycloak_issuer,
            "oss_public_endpoint": self.oss_public_endpoint,
        }
        invalid.update(
            name
            for name, value in https_fields.items()
            if value and urlparse(value).scheme.lower() != "https"
        )

        database = urlparse(self.database_url)
        if database.username == "platform" and database.password == "platform":
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
