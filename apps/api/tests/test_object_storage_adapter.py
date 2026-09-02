import asyncio
import logging

import pytest

from platform_api.modules.artifact.storage import (
    AliyunOssObjectStorageAdapter,
    CompletedPart,
    MinioObjectStorageAdapter,
    ObjectMetadata,
    ObjectStorageError,
    PresignedRequest,
    RetryPolicy,
    StorageErrorCode,
    StorageGatewayError,
    StorageProfile,
)

OBJECT_KEY = "v1/o/0123456789abcdef0123456789abcdef"
SECRET_URL = "https://example.invalid/object?X-Amz-Credential=secret-access-key"
UPLOAD_ID = "sensitive-upload-id"


class FakeGateway:
    def __init__(self) -> None:
        self.failures: list[StorageErrorCode] = []
        self.calls: list[tuple[str, object]] = []

    def _maybe_fail(self) -> None:
        if self.failures:
            raise StorageGatewayError(self.failures.pop(0))

    async def create_multipart_upload(self, bucket: str, object_key: str, content_type: str) -> str:
        self.calls.append(("create", (bucket, object_key, content_type)))
        self._maybe_fail()
        return UPLOAD_ID

    async def presign_upload_part(self, bucket: str, object_key: str, upload_id: str, part_number: int, expires_in_seconds: int) -> str:
        self.calls.append(("sign_part", part_number))
        self._maybe_fail()
        return SECRET_URL

    async def complete_multipart_upload(self, bucket: str, object_key: str, upload_id: str, parts: list[CompletedPart]) -> None:
        self.calls.append(("complete", tuple(parts)))
        self._maybe_fail()

    async def abort_multipart_upload(self, bucket: str, object_key: str, upload_id: str) -> None:
        self.calls.append(("abort", upload_id))
        self._maybe_fail()

    async def head_object(self, bucket: str, object_key: str) -> ObjectMetadata:
        self.calls.append(("head", object_key))
        self._maybe_fail()
        return ObjectMetadata(123, "etag", "application/octet-stream", "crc64")

    async def presign_download(self, bucket: str, object_key: str, expires_in_seconds: int, download_name: str) -> str:
        self.calls.append(("download", download_name))
        self._maybe_fail()
        return SECRET_URL

    async def delete_object(self, bucket: str, object_key: str) -> None:
        self.calls.append(("delete", object_key))
        self._maybe_fail()


def minio_adapter(gateway: FakeGateway, **policy: object) -> MinioObjectStorageAdapter:
    return MinioObjectStorageAdapter(
        StorageProfile("minio", "http://minio:9000", "demo"),
        gateway,
        retry_policy=RetryPolicy(**policy),
    )


@pytest.mark.asyncio
async def test_port_supports_multipart_head_download_and_delete() -> None:
    gateway = FakeGateway()
    adapter = minio_adapter(gateway)

    assert await adapter.start_multipart(OBJECT_KEY, "application/octet-stream") == UPLOAD_ID
    signed = await adapter.sign_upload_part(OBJECT_KEY, UPLOAD_ID, 1, 300)
    assert signed.url == SECRET_URL
    assert "secret-access-key" not in repr(signed)
    await adapter.complete_multipart(OBJECT_KEY, UPLOAD_ID, [CompletedPart(1, "etag")])
    assert (await adapter.head(OBJECT_KEY)).size_bytes == 123
    assert (await adapter.sign_download(OBJECT_KEY, 600, "file.bin")).url == SECRET_URL
    await adapter.abort_multipart(OBJECT_KEY, UPLOAD_ID)
    await adapter.delete(OBJECT_KEY)

    assert [call[0] for call in gateway.calls] == [
        "create", "sign_part", "complete", "head", "download", "abort", "delete"
    ]


@pytest.mark.asyncio
async def test_retry_is_limited_to_temporary_errors(caplog: pytest.LogCaptureFixture) -> None:
    gateway = FakeGateway()
    gateway.failures = [StorageErrorCode.TEMPORARY_UNAVAILABLE, StorageErrorCode.TIMEOUT]
    adapter = minio_adapter(gateway, max_attempts=3, base_delay_seconds=0)

    with caplog.at_level(logging.WARNING):
        assert await adapter.start_multipart(OBJECT_KEY, "application/octet-stream") == UPLOAD_ID

    assert len(gateway.calls) == 3
    output = caplog.text
    assert OBJECT_KEY not in output
    assert SECRET_URL not in output
    assert UPLOAD_ID not in output


@pytest.mark.asyncio
async def test_permanent_error_is_normalized_without_raw_details() -> None:
    gateway = FakeGateway()
    gateway.failures = [StorageErrorCode.ACCESS_DENIED]

    with pytest.raises(ObjectStorageError) as captured:
        await minio_adapter(gateway).head(OBJECT_KEY)

    assert captured.value.code is StorageErrorCode.ACCESS_DENIED
    assert captured.value.retryable is False
    assert str(captured.value) == "Object storage operation failed"
    assert len(gateway.calls) == 1


@pytest.mark.asyncio
async def test_timeout_is_bounded_and_normalized() -> None:
    class SlowGateway(FakeGateway):
        async def head_object(self, bucket: str, object_key: str) -> ObjectMetadata:
            await asyncio.sleep(1)
            return await super().head_object(bucket, object_key)

    with pytest.raises(ObjectStorageError) as captured:
        await minio_adapter(
            SlowGateway(), max_attempts=1, request_timeout_seconds=0.01
        ).head(OBJECT_KEY)

    assert captured.value.code is StorageErrorCode.TIMEOUT
    assert captured.value.retryable is True


@pytest.mark.asyncio
async def test_pre_cancelled_operation_never_reaches_gateway() -> None:
    gateway = FakeGateway()
    cancelled = asyncio.Event()
    cancelled.set()

    with pytest.raises(ObjectStorageError) as captured:
        await minio_adapter(gateway).delete(OBJECT_KEY, cancellation=cancelled)

    assert captured.value.code is StorageErrorCode.CANCELLED
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_cancellation_interrupts_retry_backoff() -> None:
    gateway = FakeGateway()
    gateway.failures = [StorageErrorCode.TEMPORARY_UNAVAILABLE]
    cancelled = asyncio.Event()
    adapter = minio_adapter(gateway, max_attempts=3, base_delay_seconds=1)

    task = asyncio.create_task(adapter.head(OBJECT_KEY, cancellation=cancelled))
    await asyncio.sleep(0.02)
    cancelled.set()

    with pytest.raises(ObjectStorageError) as captured:
        await task
    assert captured.value.code is StorageErrorCode.CANCELLED
    assert len(gateway.calls) == 1


@pytest.mark.parametrize("part_number", [0, 10_001])
@pytest.mark.asyncio
async def test_invalid_part_number_is_rejected_before_gateway(part_number: int) -> None:
    gateway = FakeGateway()
    with pytest.raises(ObjectStorageError) as captured:
        await minio_adapter(gateway).sign_upload_part(
            OBJECT_KEY, UPLOAD_ID, part_number, 300
        )
    assert captured.value.code is StorageErrorCode.INVALID_REQUEST
    assert gateway.calls == []


def test_provider_specific_adapters_reject_wrong_profiles() -> None:
    gateway = FakeGateway()
    with pytest.raises(ValueError, match="provider=minio"):
        MinioObjectStorageAdapter(StorageProfile("aliyun_oss", "https://x", "b", "r"), gateway)
    with pytest.raises(ValueError, match="region"):
        AliyunOssObjectStorageAdapter(StorageProfile("aliyun_oss", "https://x", "b"), gateway)

    adapter = AliyunOssObjectStorageAdapter(
        StorageProfile(
            "aliyun_oss",
            "https://oss-cn-hangzhou.aliyuncs.com",
            "aiautoplatform",
            "cn-hangzhou",
        ),
        gateway,
    )
    assert adapter is not None


def test_presigned_request_repr_never_contains_url() -> None:
    request = PresignedRequest(SECRET_URL, 600)
    assert SECRET_URL not in repr(request)
    assert "redacted" in repr(request)
