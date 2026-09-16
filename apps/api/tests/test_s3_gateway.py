from urllib.parse import parse_qs, urlparse

import pytest
from pydantic import SecretStr

from platform_api.common.public_network import PublicNetworkPolicyError
from platform_api.modules.artifact.s3_gateway import SafeS3Gateway
from platform_api.modules.artifact.storage_runtime import build_object_storage
from platform_api.settings import Settings


def gateway(provider="minio", *, allow=False, resolver=lambda _h, _p: ("127.0.0.1",)):
    return SafeS3Gateway(
        provider=provider,
        internal_endpoint="http://minio:9000"
        if provider == "minio"
        else "https://oss-cn-hangzhou.aliyuncs.com",
        public_endpoint="http://storage.example"
        if provider == "minio"
        else "https://oss-cn-hangzhou.aliyuncs.com",
        region="us-east-1" if provider == "minio" else "cn-hangzhou",
        access_key_id="test-id",
        access_key_secret="test-secret",
        allow_insecure_private_transport=allow,
        resolver=resolver,
    )


def test_provider_addressing_and_presign_are_scoped() -> None:
    minio = gateway()
    oss = gateway("aliyun_oss", resolver=lambda _h, _p: ("93.184.216.34",))
    assert (
        minio._url(minio.public_endpoint, "bucket", "v1/o/key")
        == "http://storage.example/bucket/v1/o/key"
    )
    assert (
        oss._url(oss.public_endpoint, "bucket", "v1/o/key")
        == "https://bucket.oss-cn-hangzhou.aliyuncs.com/v1/o/key"
    )
    signed = minio._presigned(
        "PUT", "http://storage.example/bucket/key?partNumber=1&uploadId=id", 300
    )
    query = parse_qs(urlparse(signed).query)
    assert query["X-Amz-Expires"] == ["300"]
    assert "X-Amz-Signature" in query
    assert "test-secret" not in signed


def test_network_policy_requires_explicit_private_http_and_rejects_private_https() -> (
    None
):
    with pytest.raises(PublicNetworkPolicyError, match="requires HTTPS"):
        gateway()._addresses("http://minio:9000")
    assert gateway(allow=True)._addresses("http://minio:9000") == ("127.0.0.1",)
    with pytest.raises(PublicNetworkPolicyError, match="outside the public Internet"):
        gateway("aliyun_oss")._addresses("https://oss.example")


def test_runtime_is_fail_closed_and_secrets_are_redacted() -> None:
    build_object_storage.cache_clear()
    assert build_object_storage(Settings(oss_public_endpoint=None)) is None
    settings = Settings(
        oss_provider="minio",
        oss_region="us-east-1",
        oss_internal_endpoint="http://minio:9000",
        oss_public_endpoint="http://storage.example",
        oss_bucket="bucket",
        oss_access_key_id=SecretStr("test-id"),
        oss_access_key_secret=SecretStr("test-secret"),
        allow_insecure_private_service_transport=True,
    )
    assert build_object_storage(settings) is not None
    assert "test-secret" not in repr(settings)
