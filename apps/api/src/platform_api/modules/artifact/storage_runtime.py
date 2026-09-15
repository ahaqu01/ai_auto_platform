from functools import lru_cache

from platform_api.modules.artifact.s3_gateway import SafeS3Gateway
from platform_api.modules.artifact.storage import (
    AliyunOssObjectStorageAdapter,
    MinioObjectStorageAdapter,
    ObjectStoragePort,
    StorageProfile,
)
from platform_api.settings import Settings


@lru_cache
def build_object_storage(settings: Settings) -> ObjectStoragePort | None:
    required = (
        settings.oss_internal_endpoint,
        settings.oss_public_endpoint,
        settings.oss_bucket,
        settings.oss_access_key_id,
        settings.oss_access_key_secret,
    )
    if not all(required):
        return None
    gateway = SafeS3Gateway(
        provider=settings.oss_provider,
        internal_endpoint=settings.oss_internal_endpoint or "",
        public_endpoint=settings.oss_public_endpoint or "",
        region=settings.oss_region,
        access_key_id=settings.oss_access_key_id.get_secret_value(),
        access_key_secret=settings.oss_access_key_secret.get_secret_value(),
        session_token=(
            settings.oss_session_token.get_secret_value()
            if settings.oss_session_token
            else None
        ),
        allow_insecure_private_transport=(
            settings.allow_insecure_private_service_transport
        ),
    )
    profile = StorageProfile(
        settings.oss_provider,
        settings.oss_public_endpoint or "",
        settings.oss_bucket or "",
        settings.oss_region,
    )
    adapter = (
        MinioObjectStorageAdapter(profile, gateway)
        if settings.oss_provider == "minio"
        else AliyunOssObjectStorageAdapter(profile, gateway)
    )
    return adapter
