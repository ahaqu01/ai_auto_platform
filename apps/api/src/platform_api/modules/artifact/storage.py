from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypeVar

logger = logging.getLogger(__name__)
T = TypeVar("T")


class StorageErrorCode(StrEnum):
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    ACCESS_DENIED = "ACCESS_DENIED"
    INVALID_REQUEST = "INVALID_REQUEST"
    TIMEOUT = "TIMEOUT"
    TEMPORARY_UNAVAILABLE = "TEMPORARY_UNAVAILABLE"
    CANCELLED = "CANCELLED"
    INTERNAL = "INTERNAL"


class ObjectStorageError(Exception):
    def __init__(self, code: StorageErrorCode, safe_detail: str, *, retryable: bool) -> None:
        super().__init__(safe_detail)
        self.code = code
        self.safe_detail = safe_detail
        self.retryable = retryable

    def __str__(self) -> str:
        return self.safe_detail


class StorageGatewayError(Exception):
    """Sanitized gateway failure; raw SDK exceptions must not cross this boundary."""

    def __init__(self, code: StorageErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


@dataclass(frozen=True, slots=True)
class StorageProfile:
    provider: str
    endpoint: str
    bucket: str
    region: str | None = None


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    request_timeout_seconds: float = 10.0
    base_delay_seconds: float = 0.05

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds must not be negative")


@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    size_bytes: int
    etag: str | None
    content_type: str | None
    checksum_crc64: str | None = None


@dataclass(frozen=True, slots=True)
class CompletedPart:
    part_number: int
    etag: str


@dataclass(frozen=True, slots=True, repr=False)
class PresignedRequest:
    url: str
    expires_in_seconds: int

    def __repr__(self) -> str:
        return (
            "PresignedRequest(url='<redacted>', "
            f"expires_in_seconds={self.expires_in_seconds})"
        )


class CancellationSignal(Protocol):
    def is_set(self) -> bool: ...


class S3CompatibleGateway(Protocol):
    async def create_multipart_upload(
        self, bucket: str, object_key: str, content_type: str
    ) -> str: ...

    async def presign_upload_part(
        self,
        bucket: str,
        object_key: str,
        upload_id: str,
        part_number: int,
        expires_in_seconds: int,
    ) -> str: ...

    async def complete_multipart_upload(
        self,
        bucket: str,
        object_key: str,
        upload_id: str,
        parts: Sequence[CompletedPart],
    ) -> None: ...

    async def abort_multipart_upload(
        self, bucket: str, object_key: str, upload_id: str
    ) -> None: ...

    async def head_object(self, bucket: str, object_key: str) -> ObjectMetadata: ...

    async def presign_download(
        self,
        bucket: str,
        object_key: str,
        expires_in_seconds: int,
        download_name: str,
    ) -> str: ...

    async def delete_object(self, bucket: str, object_key: str) -> None: ...


class ObjectStoragePort(Protocol):
    async def start_multipart(
        self, object_key: str, content_type: str, *, cancellation: CancellationSignal | None = None
    ) -> str: ...

    async def sign_upload_part(
        self,
        object_key: str,
        upload_id: str,
        part_number: int,
        expires_in_seconds: int,
        *,
        cancellation: CancellationSignal | None = None,
    ) -> PresignedRequest: ...

    async def complete_multipart(
        self,
        object_key: str,
        upload_id: str,
        parts: Sequence[CompletedPart],
        *,
        cancellation: CancellationSignal | None = None,
    ) -> None: ...

    async def abort_multipart(
        self,
        object_key: str,
        upload_id: str,
        *,
        cancellation: CancellationSignal | None = None,
    ) -> None: ...

    async def head(
        self, object_key: str, *, cancellation: CancellationSignal | None = None
    ) -> ObjectMetadata: ...

    async def sign_download(
        self,
        object_key: str,
        expires_in_seconds: int,
        download_name: str,
        *,
        cancellation: CancellationSignal | None = None,
    ) -> PresignedRequest: ...

    async def delete(
        self, object_key: str, *, cancellation: CancellationSignal | None = None
    ) -> None: ...


class S3CompatibleObjectStorageAdapter:
    def __init__(
        self,
        profile: StorageProfile,
        gateway: S3CompatibleGateway,
        *,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._profile = profile
        self._gateway = gateway
        self._retry = retry_policy or RetryPolicy()

    async def start_multipart(
        self, object_key: str, content_type: str, *, cancellation: CancellationSignal | None = None
    ) -> str:
        return await self._run(
            "start_multipart",
            object_key,
            lambda: self._gateway.create_multipart_upload(
                self._profile.bucket, object_key, content_type
            ),
            cancellation,
        )

    async def sign_upload_part(
        self,
        object_key: str,
        upload_id: str,
        part_number: int,
        expires_in_seconds: int,
        *,
        cancellation: CancellationSignal | None = None,
    ) -> PresignedRequest:
        if part_number < 1 or part_number > 10_000:
            raise ObjectStorageError(
                StorageErrorCode.INVALID_REQUEST,
                "Invalid multipart part number",
                retryable=False,
            )
        url = await self._run(
            "sign_upload_part",
            object_key,
            lambda: self._gateway.presign_upload_part(
                self._profile.bucket,
                object_key,
                upload_id,
                part_number,
                expires_in_seconds,
            ),
            cancellation,
        )
        return PresignedRequest(url=url, expires_in_seconds=expires_in_seconds)

    async def complete_multipart(
        self,
        object_key: str,
        upload_id: str,
        parts: Sequence[CompletedPart],
        *,
        cancellation: CancellationSignal | None = None,
    ) -> None:
        await self._run(
            "complete_multipart",
            object_key,
            lambda: self._gateway.complete_multipart_upload(
                self._profile.bucket, object_key, upload_id, parts
            ),
            cancellation,
        )

    async def abort_multipart(
        self,
        object_key: str,
        upload_id: str,
        *,
        cancellation: CancellationSignal | None = None,
    ) -> None:
        await self._run(
            "abort_multipart",
            object_key,
            lambda: self._gateway.abort_multipart_upload(
                self._profile.bucket, object_key, upload_id
            ),
            cancellation,
        )

    async def head(
        self, object_key: str, *, cancellation: CancellationSignal | None = None
    ) -> ObjectMetadata:
        return await self._run(
            "head", object_key, lambda: self._gateway.head_object(self._profile.bucket, object_key), cancellation
        )

    async def sign_download(
        self,
        object_key: str,
        expires_in_seconds: int,
        download_name: str,
        *,
        cancellation: CancellationSignal | None = None,
    ) -> PresignedRequest:
        url = await self._run(
            "sign_download",
            object_key,
            lambda: self._gateway.presign_download(
                self._profile.bucket,
                object_key,
                expires_in_seconds,
                download_name,
            ),
            cancellation,
        )
        return PresignedRequest(url=url, expires_in_seconds=expires_in_seconds)

    async def delete(
        self, object_key: str, *, cancellation: CancellationSignal | None = None
    ) -> None:
        await self._run(
            "delete", object_key, lambda: self._gateway.delete_object(self._profile.bucket, object_key), cancellation
        )

    async def _run(
        self,
        operation: str,
        object_key: str,
        call: Callable[[], Awaitable[T]],
        cancellation: CancellationSignal | None,
    ) -> T:
        key_ref = hashlib.sha256(object_key.encode()).hexdigest()[:12]
        for attempt in range(1, self._retry.max_attempts + 1):
            if cancellation and cancellation.is_set():
                raise ObjectStorageError(
                    StorageErrorCode.CANCELLED, "Storage operation cancelled", retryable=False
                )
            try:
                return await asyncio.wait_for(
                    call(), timeout=self._retry.request_timeout_seconds
                )
            except TimeoutError:
                code = StorageErrorCode.TIMEOUT
            except StorageGatewayError as exc:
                code = exc.code
            retryable = code in {
                StorageErrorCode.TIMEOUT,
                StorageErrorCode.TEMPORARY_UNAVAILABLE,
            }
            logger.warning(
                "object_storage_operation_failed",
                extra={
                    "provider": self._profile.provider,
                    "operation": operation,
                    "key_ref": key_ref,
                    "attempt": attempt,
                    "error_code": code.value,
                },
            )
            if not retryable or attempt >= self._retry.max_attempts:
                raise ObjectStorageError(
                    code, "Object storage operation failed", retryable=retryable
                ) from None
            if cancellation:
                try:
                    await asyncio.wait_for(
                        _wait_for_cancellation(cancellation),
                        timeout=self._retry.base_delay_seconds * (2 ** (attempt - 1)),
                    )
                except TimeoutError:
                    continue
                raise ObjectStorageError(
                    StorageErrorCode.CANCELLED, "Storage operation cancelled", retryable=False
                )
            await asyncio.sleep(self._retry.base_delay_seconds * (2 ** (attempt - 1)))
        raise AssertionError("unreachable")


async def _wait_for_cancellation(signal: CancellationSignal) -> None:
    while not signal.is_set():
        await asyncio.sleep(0.01)


class MinioObjectStorageAdapter(S3CompatibleObjectStorageAdapter):
    def __init__(self, profile: StorageProfile, gateway: S3CompatibleGateway, **kwargs: object) -> None:
        if profile.provider != "minio":
            raise ValueError("MinIO adapter requires provider=minio")
        super().__init__(profile, gateway, **kwargs)


class AliyunOssObjectStorageAdapter(S3CompatibleObjectStorageAdapter):
    def __init__(self, profile: StorageProfile, gateway: S3CompatibleGateway, **kwargs: object) -> None:
        if profile.provider != "aliyun_oss" or not profile.region:
            raise ValueError("Aliyun OSS adapter requires provider=aliyun_oss and region")
        super().__init__(profile, gateway, **kwargs)
