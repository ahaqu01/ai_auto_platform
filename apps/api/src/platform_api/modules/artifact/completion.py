from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Protocol

from platform_api.modules.artifact.storage import CompletedPart, ObjectMetadata


class VerificationStoragePort(Protocol):
    async def complete_multipart(
        self,
        object_key: str,
        upload_id: str,
        parts: Sequence[CompletedPart],
        **kwargs: object,
    ) -> None: ...

    async def head(self, object_key: str, **kwargs: object) -> ObjectMetadata: ...

    def read_chunks(
        self, object_key: str, **kwargs: object
    ) -> AsyncIterator[bytes]: ...


@dataclass(frozen=True, slots=True)
class VerificationResult:
    metadata: ObjectMetadata
    verified_sha256: str


async def verify_object(
    storage: VerificationStoragePort,
    object_key: str,
) -> VerificationResult:
    metadata = await storage.head(object_key)
    digest = hashlib.sha256()
    streamed_size = 0
    async for chunk in storage.read_chunks(object_key):
        if not chunk:
            continue
        digest.update(chunk)
        streamed_size += len(chunk)
    if streamed_size != metadata.size_bytes:
        metadata = ObjectMetadata(
            size_bytes=streamed_size,
            etag=metadata.etag,
            content_type=metadata.content_type,
            checksum_crc64=metadata.checksum_crc64,
        )
    return VerificationResult(metadata=metadata, verified_sha256=digest.hexdigest())
