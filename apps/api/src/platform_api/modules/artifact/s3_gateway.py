from __future__ import annotations

import asyncio
import http.client
import logging
import socket
import ssl
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from ipaddress import ip_address
from urllib.parse import quote, urlencode, urlparse
from xml.etree import ElementTree

from botocore.auth import S3SigV4Auth, S3SigV4QueryAuth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials

from platform_api.auth.verifier import PinnedHTTPSConnection
from platform_api.common.public_network import (
    AddressResolver,
    PublicNetworkPolicyError,
    resolve_hostname,
    validated_public_addresses,
)
from platform_api.modules.artifact.storage import (
    CompletedPart,
    ObjectMetadata,
    StorageErrorCode,
    StorageGatewayError,
    StorageObjectRef,
)


def _deny_signing_debug(_record: logging.LogRecord) -> bool:
    return False


# The signing library debug output contains canonical paths and signatures.
logging.getLogger("botocore.auth").addFilter(_deny_signing_debug)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(
        self,
        host: str,
        port: int,
        *,
        verified_addresses: tuple[str, ...],
        pinned_address: str,
        timeout: float,
    ) -> None:
        super().__init__(host, port, timeout=timeout)
        self.verified = frozenset(ip_address(value) for value in verified_addresses)
        self.pinned = pinned_address

    def connect(self) -> None:
        sock = socket.create_connection(
            (self.pinned, self.port), self.timeout, self.source_address
        )
        try:
            if (
                ip_address(str(sock.getpeername()[0]).split("%", 1)[0])
                not in self.verified
            ):
                raise PublicNetworkPolicyError(
                    "storage socket peer is outside verified addresses"
                )
            self.sock = sock
        except Exception:
            sock.close()
            raise


class SafeS3Gateway:
    """S3-compatible gateway with DNS validation and pinned network peers."""

    def __init__(
        self,
        *,
        provider: str,
        internal_endpoint: str,
        public_endpoint: str,
        region: str,
        access_key_id: str,
        access_key_secret: str,
        session_token: str | None = None,
        allow_insecure_private_transport: bool = False,
        resolver: AddressResolver = resolve_hostname,
        timeout_seconds: float = 10.0,
    ) -> None:
        if provider not in {"minio", "aliyun_oss"}:
            raise ValueError("unsupported object storage provider")
        for endpoint in (internal_endpoint, public_endpoint):
            parsed = urlparse(endpoint)
            if (
                not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
                or parsed.scheme not in {"http", "https"}
            ):
                raise ValueError("invalid object storage endpoint")
            if provider == "aliyun_oss" and parsed.scheme != "https":
                raise ValueError("OSS endpoints require HTTPS")
        self.provider, self.region = provider, region
        self.internal_endpoint, self.public_endpoint = (
            internal_endpoint.rstrip("/"),
            public_endpoint.rstrip("/"),
        )
        self.credentials = Credentials(access_key_id, access_key_secret, session_token)
        self.allow_insecure, self.resolver, self.timeout = (
            allow_insecure_private_transport,
            resolver,
            timeout_seconds,
        )

    def _url(
        self,
        endpoint: str,
        bucket: str,
        key: str = "",
        query: list[tuple[str, str]] | None = None,
    ) -> str:
        parsed, encoded = urlparse(endpoint), quote(key, safe="/~-._")
        if not parsed.hostname:
            raise StorageGatewayError(StorageErrorCode.INVALID_REQUEST)
        if self.provider == "aliyun_oss":
            host = f"{bucket}.{parsed.hostname}" + (
                f":{parsed.port}" if parsed.port else ""
            )
            path = f"/{encoded}" if encoded else "/"
        else:
            host, path = parsed.netloc, f"/{quote(bucket, safe='')}/" + encoded
        return f"{parsed.scheme}://{host}{path}" + (
            f"?{urlencode(query)}" if query else ""
        )

    def _signed(
        self,
        method: str,
        url: str,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> AWSRequest:
        request = AWSRequest(method=method, url=url, data=body, headers=headers or {})
        S3SigV4Auth(self.credentials, "s3", self.region).add_auth(request)
        return request

    def _presigned(self, method: str, url: str, expires: int) -> str:
        if not 1 <= expires <= 900:
            raise StorageGatewayError(StorageErrorCode.INVALID_REQUEST)
        request = AWSRequest(method=method, url=url)
        S3SigV4QueryAuth(self.credentials, "s3", self.region, expires=expires).add_auth(
            request
        )
        return request.url

    def _addresses(self, url: str) -> tuple[str, ...]:
        parsed = urlparse(url)
        if parsed.scheme == "https":
            return validated_public_addresses(url, resolver=self.resolver)
        if parsed.scheme != "http" or not self.allow_insecure or not parsed.hostname:
            raise PublicNetworkPolicyError("storage endpoint requires HTTPS")
        addresses = tuple(self.resolver(parsed.hostname, parsed.port or 80))
        if not addresses:
            raise PublicNetworkPolicyError("storage endpoint returned no addresses")
        if self.provider != "minio" or not all(
            ip_address(address).is_private
            and not ip_address(address).is_link_local
            and not ip_address(address).is_unspecified
            and not ip_address(address).is_multicast
            for address in addresses
        ):
            raise PublicNetworkPolicyError(
                "private storage endpoint resolved outside approved private addresses"
            )
        return addresses

    def _open(self, request: AWSRequest):
        parsed, addresses = urlparse(request.url), self._addresses(request.url)
        target = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
        for address in addresses:
            if parsed.scheme == "https":
                connection = PinnedHTTPSConnection(
                    parsed.hostname or "",
                    parsed.port or 443,
                    verified_addresses=addresses,
                    pinned_address=address,
                    context=ssl.create_default_context(),
                    timeout=self.timeout,
                )
            else:
                connection = _PinnedHTTPConnection(
                    parsed.hostname or "",
                    parsed.port or 80,
                    verified_addresses=addresses,
                    pinned_address=address,
                    timeout=self.timeout,
                )
            try:
                connection.request(
                    request.method,
                    target,
                    body=request.body,
                    headers=dict(request.headers.items()),
                )
                response = connection.getresponse()
                if 300 <= response.status < 400:
                    response.close()
                    connection.close()
                    raise PublicNetworkPolicyError("storage redirects are not allowed")
                return connection, response
            except (OSError, http.client.HTTPException):
                connection.close()
        raise StorageGatewayError(StorageErrorCode.TEMPORARY_UNAVAILABLE) from None

    @staticmethod
    def _failure(status: int) -> StorageGatewayError:
        if status == 404:
            code = StorageErrorCode.NOT_FOUND
        elif status in {401, 403}:
            code = StorageErrorCode.ACCESS_DENIED
        elif status == 409:
            code = StorageErrorCode.CONFLICT
        elif status in {408, 429} or status >= 500:
            code = StorageErrorCode.TEMPORARY_UNAVAILABLE
        elif status >= 400:
            code = StorageErrorCode.INVALID_REQUEST
        else:
            code = StorageErrorCode.INTERNAL
        return StorageGatewayError(code)

    def _execute(self, request: AWSRequest) -> tuple[bytes, dict[str, str]]:
        connection = response = None
        try:
            connection, response = self._open(request)
            body = response.read(4 * 1024 * 1024 + 1)
            if len(body) > 4 * 1024 * 1024:
                raise StorageGatewayError(StorageErrorCode.INTERNAL)
            if not 200 <= response.status < 300:
                raise self._failure(response.status)
            return body, {name.lower(): value for name, value in response.getheaders()}
        except (PublicNetworkPolicyError, ssl.SSLError):
            raise StorageGatewayError(StorageErrorCode.ACCESS_DENIED) from None
        except (OSError, http.client.HTTPException):
            raise StorageGatewayError(StorageErrorCode.TEMPORARY_UNAVAILABLE) from None
        finally:
            if response is not None:
                response.close()
            if connection is not None:
                connection.close()

    @staticmethod
    def _xml(body: bytes):
        try:
            root = ElementTree.fromstring(body)
            if root.tag.rsplit("}", 1)[-1] == "Error":
                raise StorageGatewayError(StorageErrorCode.INVALID_REQUEST)
            return root
        except ElementTree.ParseError:
            raise StorageGatewayError(StorageErrorCode.INTERNAL) from None

    async def create_multipart_upload(
        self, bucket: str, object_key: str, content_type: str
    ) -> str:
        url = self._url(self.internal_endpoint, bucket, object_key, [("uploads", "")])
        body, _ = await asyncio.to_thread(
            self._execute,
            self._signed("POST", url, headers={"Content-Type": content_type}),
        )
        upload_id = self._xml(body).findtext("{*}UploadId")
        if not upload_id:
            raise StorageGatewayError(StorageErrorCode.INTERNAL)
        return upload_id

    async def presign_upload_part(
        self,
        bucket: str,
        object_key: str,
        upload_id: str,
        part_number: int,
        expires_in_seconds: int,
    ) -> str:
        return self._presigned(
            "PUT",
            self._url(
                self.public_endpoint,
                bucket,
                object_key,
                [("partNumber", str(part_number)), ("uploadId", upload_id)],
            ),
            expires_in_seconds,
        )

    async def complete_multipart_upload(
        self,
        bucket: str,
        object_key: str,
        upload_id: str,
        parts: Sequence[CompletedPart],
    ) -> None:
        root = ElementTree.Element("CompleteMultipartUpload")
        for item in parts:
            part = ElementTree.SubElement(root, "Part")
            ElementTree.SubElement(part, "PartNumber").text = str(item.part_number)
            ElementTree.SubElement(part, "ETag").text = '"' + item.etag.strip('"') + '"'
        body = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
        url = self._url(
            self.internal_endpoint, bucket, object_key, [("uploadId", upload_id)]
        )
        result, _ = await asyncio.to_thread(
            self._execute,
            self._signed("POST", url, body, {"Content-Type": "application/xml"}),
        )
        self._xml(result)

    async def abort_multipart_upload(
        self, bucket: str, object_key: str, upload_id: str
    ) -> None:
        await asyncio.to_thread(
            self._execute,
            self._signed(
                "DELETE",
                self._url(
                    self.internal_endpoint,
                    bucket,
                    object_key,
                    [("uploadId", upload_id)],
                ),
            ),
        )

    async def head_object(self, bucket: str, object_key: str) -> ObjectMetadata:
        _, headers = await asyncio.to_thread(
            self._execute,
            self._signed("HEAD", self._url(self.internal_endpoint, bucket, object_key)),
        )
        return ObjectMetadata(
            int(headers.get("content-length", "0")),
            headers.get("etag", "").strip('"') or None,
            headers.get("content-type"),
            headers.get("x-oss-hash-crc64ecma"),
        )

    async def presign_download(
        self, bucket: str, object_key: str, expires_in_seconds: int, download_name: str
    ) -> str:
        disposition = "attachment; filename*=UTF-8''" + quote(download_name, safe="")
        return self._presigned(
            "GET",
            self._url(
                self.public_endpoint,
                bucket,
                object_key,
                [("response-content-disposition", disposition)],
            ),
            expires_in_seconds,
        )

    async def delete_object(self, bucket: str, object_key: str) -> None:
        await asyncio.to_thread(
            self._execute,
            self._signed(
                "DELETE", self._url(self.internal_endpoint, bucket, object_key)
            ),
        )

    async def read_object_chunks(
        self, bucket: str, object_key: str
    ) -> AsyncIterator[bytes]:
        connection = response = None
        try:
            connection, response = await asyncio.to_thread(
                self._open,
                self._signed(
                    "GET", self._url(self.internal_endpoint, bucket, object_key)
                ),
            )
            if not 200 <= response.status < 300:
                raise self._failure(response.status)
            while chunk := await asyncio.to_thread(response.read, 1024 * 1024):
                yield chunk
        except (PublicNetworkPolicyError, ssl.SSLError):
            raise StorageGatewayError(StorageErrorCode.ACCESS_DENIED) from None
        except (OSError, http.client.HTTPException):
            raise StorageGatewayError(StorageErrorCode.TEMPORARY_UNAVAILABLE) from None
        finally:
            if response is not None:
                response.close()
            if connection is not None:
                connection.close()

    async def list_objects(
        self, bucket: str, prefix: str
    ) -> AsyncIterator[StorageObjectRef]:
        continuation: str | None = None
        while True:
            query = [("list-type", "2"), ("prefix", prefix)] + (
                [("continuation-token", continuation)] if continuation else []
            )
            body, _ = await asyncio.to_thread(
                self._execute,
                self._signed(
                    "GET", self._url(self.internal_endpoint, bucket, query=query)
                ),
            )
            root = self._xml(body)
            for item in root.findall("{*}Contents"):
                key, modified = (
                    item.findtext("{*}Key"),
                    item.findtext("{*}LastModified"),
                )
                if key and modified:
                    yield StorageObjectRef(key, datetime.fromisoformat(modified))
            if root.findtext("{*}IsTruncated", "false").lower() != "true":
                break
            continuation = root.findtext("{*}NextContinuationToken")
            if not continuation:
                raise StorageGatewayError(StorageErrorCode.INTERNAL)
