"""Destructive only inside the dedicated v1/o/close01-test prefix."""

import asyncio
import hashlib
import http.client
import os
from urllib.parse import urlparse

from platform_api.modules.artifact.s3_gateway import SafeS3Gateway
from platform_api.modules.artifact.storage import (
    CompletedPart,
    StorageErrorCode,
    StorageGatewayError,
)


async def main() -> None:
    payload = b"M2-CLOSE-01-real-minio\n" * 300000
    key = "v1/o/close01-test"
    gateway = SafeS3Gateway(
        provider="minio",
        internal_endpoint=os.environ["OSS_INTERNAL_ENDPOINT"],
        public_endpoint=os.environ["OSS_PUBLIC_ENDPOINT"],
        region=os.environ["OSS_REGION"],
        access_key_id=os.environ["OSS_ACCESS_KEY_ID"],
        access_key_secret=os.environ["OSS_ACCESS_KEY_SECRET"],
        allow_insecure_private_transport=True,
    )
    try:
        await asyncio.to_thread(
            gateway._execute,
            gateway._signed("PUT", gateway._url(gateway.internal_endpoint, "demo")),
        )
    except StorageGatewayError as exc:
        assert exc.code is StorageErrorCode.CONFLICT
    upload_id = await gateway.create_multipart_upload("demo", key, "application/octet-stream")
    try:
        signed = await gateway.presign_upload_part("demo", key, upload_id, 1, 300)
        parsed = urlparse(signed)
        connection = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=30)
        connection.request(
            "PUT",
            parsed.path + "?" + parsed.query,
            body=payload,
            headers={"Content-Length": str(len(payload))},
        )
        response = connection.getresponse()
        assert response.status == 200, response.status
        etag = (response.getheader("ETag") or "").strip('"')
        response.read()
        response.close()
        connection.close()
        assert etag
        await gateway.complete_multipart_upload("demo", key, upload_id, [CompletedPart(1, etag)])
        metadata = await gateway.head_object("demo", key)
        assert metadata.size_bytes == len(payload)
        digest = hashlib.sha256()
        async for chunk in gateway.read_object_chunks("demo", key):
            digest.update(chunk)
        assert digest.digest() == hashlib.sha256(payload).digest()
        assert key in [item.object_key async for item in gateway.list_objects("demo", "v1/o/")]
        download = await gateway.presign_download("demo", key, 300, "验收.bin")
        assert "X-Amz-Signature" in download
    finally:
        await gateway.delete_object("demo", key)
    try:
        await gateway.head_object("demo", key)
    except StorageGatewayError as exc:
        assert exc.code is StorageErrorCode.NOT_FOUND
    else:
        raise AssertionError("test object was not deleted")
    print("PASS: real MinIO gateway multipart/read/list/download/delete")


asyncio.run(main())
