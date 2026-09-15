import asyncio
from datetime import UTC, datetime

import pytest

from platform_api.modules.artifact.s3_gateway import SafeS3Gateway
from platform_api.modules.artifact.storage import (
    CompletedPart,
    StorageErrorCode,
    StorageGatewayError,
)


def gateway():
    return SafeS3Gateway(
        provider="minio",
        internal_endpoint="http://minio:9000",
        public_endpoint="http://web",
        region="us-east-1",
        access_key_id="test",
        access_key_secret="test",
        allow_insecure_private_transport=True,
        resolver=lambda _h, _p: ("172.18.0.2",),
    )


@pytest.mark.asyncio
async def test_all_control_operations_and_xml(monkeypatch):
    client = gateway()
    calls = []
    responses = iter(
        [
            (
                b"<InitiateMultipartUploadResult><UploadId>upload-1</UploadId></InitiateMultipartUploadResult>",
                {},
            ),
            (b"<CompleteMultipartUploadResult/>", {}),
            (b"", {}),
            (
                b"",
                {
                    "content-length": "7",
                    "etag": '"etag"',
                    "content-type": "text/plain",
                    "x-oss-hash-crc64ecma": "9",
                },
            ),
            (b"", {}),
        ]
    )

    def execute(request):
        calls.append((request.method, request.url, bytes(request.body or b"")))
        return next(responses)

    monkeypatch.setattr(client, "_execute", execute)
    upload_id = await client.create_multipart_upload("bucket", "v1/o/key", "text/plain")
    assert upload_id == "upload-1"
    await client.complete_multipart_upload(
        "bucket", "v1/o/key", upload_id, [CompletedPart(1, "etag")]
    )
    await client.abort_multipart_upload("bucket", "v1/o/key", upload_id)
    metadata = await client.head_object("bucket", "v1/o/key")
    await client.delete_object("bucket", "v1/o/key")
    assert (
        metadata.size_bytes == 7
        and metadata.etag == "etag"
        and metadata.checksum_crc64 == "9"
    )
    assert [item[0] for item in calls] == ["POST", "POST", "DELETE", "HEAD", "DELETE"]
    assert b"&quot;" not in calls[1][2] and b'"etag"' in calls[1][2]


@pytest.mark.asyncio
async def test_list_paginates_and_parses_timestamps(monkeypatch):
    client = gateway()
    pages = iter(
        [
            b"<ListBucketResult><IsTruncated>true</IsTruncated><NextContinuationToken>next</NextContinuationToken><Contents><Key>v1/o/a</Key><LastModified>2026-09-15T00:00:00Z</LastModified></Contents></ListBucketResult>",
            b"<ListBucketResult><IsTruncated>false</IsTruncated><Contents><Key>v1/o/b</Key><LastModified>2026-09-15T00:00:01Z</LastModified></Contents></ListBucketResult>",
        ]
    )
    monkeypatch.setattr(client, "_execute", lambda _request: (next(pages), {}))
    items = [item async for item in client.list_objects("bucket", "v1/o/")]
    assert [item.object_key for item in items] == ["v1/o/a", "v1/o/b"]
    assert items[0].last_modified == datetime(2026, 9, 15, tzinfo=UTC)


@pytest.mark.asyncio
async def test_read_streams_and_closes(monkeypatch):
    client = gateway()

    class Response:
        status = 200

        def __init__(self):
            self.chunks = [b"abc", b"def", b""]
            self.closed = False

        def read(self, _size):
            return self.chunks.pop(0)

        def close(self):
            self.closed = True

    class Connection:
        closed = False

        def close(self):
            self.closed = True

    response, connection = Response(), Connection()
    monkeypatch.setattr(client, "_open", lambda _request: (connection, response))
    assert (
        b"".join(
            [chunk async for chunk in client.read_object_chunks("bucket", "v1/o/key")]
        )
        == b"abcdef"
    )
    assert response.closed and connection.closed


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (404, StorageErrorCode.NOT_FOUND),
        (401, StorageErrorCode.ACCESS_DENIED),
        (409, StorageErrorCode.CONFLICT),
        (429, StorageErrorCode.TEMPORARY_UNAVAILABLE),
        (500, StorageErrorCode.TEMPORARY_UNAVAILABLE),
        (400, StorageErrorCode.INVALID_REQUEST),
        (200, StorageErrorCode.INTERNAL),
    ],
)
def test_status_mapping(status, code):
    assert gateway()._failure(status).code is code


def test_missing_upload_id_and_continuation_are_rejected(monkeypatch):
    client = gateway()
    monkeypatch.setattr(client, "_execute", lambda _request: (b"<Result/>", {}))
    with pytest.raises(StorageGatewayError):
        asyncio.run(client.create_multipart_upload("bucket", "key", "text/plain"))

    monkeypatch.setattr(
        client,
        "_execute",
        lambda _request: (
            b"<ListBucketResult><IsTruncated>true</IsTruncated></ListBucketResult>",
            {},
        ),
    )

    async def collect():
        return [item async for item in client.list_objects("bucket", "v1/o/")]

    with pytest.raises(StorageGatewayError):
        asyncio.run(collect())
