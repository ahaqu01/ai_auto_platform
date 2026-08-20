from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["local", "test", "staging", "production"] = "local"
    app_name: str = "ai-auto-platform"
    app_version: str = "0.1.0"
    database_url: str | None = None
    redis_url: str | None = None
    temporal_address: str | None = None
    keycloak_issuer: str | None = None
    oss_public_endpoint: str | None = None
    oss_internal_endpoint: str | None = None
    oss_bucket: str | None = None

    def validate_production(self) -> None:
        if self.app_env != "production":
            return
        required = {
            "database_url": self.database_url,
            "redis_url": self.redis_url,
            "temporal_address": self.temporal_address,
            "keycloak_issuer": self.keycloak_issuer,
            "oss_public_endpoint": self.oss_public_endpoint,
            "oss_internal_endpoint": self.oss_internal_endpoint,
            "oss_bucket": self.oss_bucket,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"Missing production settings: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_production()
    return settings

