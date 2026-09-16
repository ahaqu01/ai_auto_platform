"""Read-only public transport probe; uses deliberately invalid credentials."""

import asyncio

from platform_api.modules.artifact.s3_gateway import SafeS3Gateway
from platform_api.modules.artifact.storage import StorageErrorCode, StorageGatewayError


async def main() -> None:
    gateway = SafeS3Gateway(
        provider="aliyun_oss",
        internal_endpoint="https://oss-cn-hangzhou.aliyuncs.com",
        public_endpoint="https://oss-cn-hangzhou.aliyuncs.com",
        region="cn-hangzhou",
        access_key_id="M2CLOSE01INVALIDPROBE",
        access_key_secret="invalid-probe-secret-never-authorized",
    )
    request = gateway._signed(
        "HEAD",
        gateway._url(gateway.internal_endpoint, "aiautoplatform", "v1/o/transport-probe"),
    )
    try:
        await asyncio.to_thread(gateway._execute, request)
    except StorageGatewayError as exc:
        assert exc.code in {
            StorageErrorCode.ACCESS_DENIED,
            StorageErrorCode.NOT_FOUND,
            StorageErrorCode.INVALID_REQUEST,
        }
    else:
        raise AssertionError("invalid credentials unexpectedly succeeded")
    print("PASS: pinned OSS HTTPS transport reached a normalized denial")


asyncio.run(main())
