import logging
from typing import ClassVar

import pytest

from platform_api.common.public_network import PublicNetworkPolicyError
from platform_api.modules.artifact import s3_gateway
from platform_api.modules.artifact.storage import StorageErrorCode, StorageGatewayError


def gateway(resolver=lambda _h, _p: ("93.184.216.34",)):
    return s3_gateway.SafeS3Gateway(
        provider="aliyun_oss",
        internal_endpoint="https://oss.example",
        public_endpoint="https://oss.example",
        region="cn-hangzhou",
        access_key_id="sensitive-test-id",
        access_key_secret="sensitive-test-secret",
        resolver=resolver,
    )


class Response:
    status = 302

    def read(self, _size=-1):
        return b""

    def getheaders(self):
        return []

    def close(self):
        return None


class Connection:
    calls: ClassVar[list[tuple[str, int, str]]] = []

    def __init__(self, host, port, **kwargs):
        self.calls.append((host, port, kwargs["pinned_address"]))

    def request(self, *_args, **_kwargs):
        return None

    def getresponse(self):
        return Response()

    def close(self):
        return None


def test_redirect_is_rejected_without_following_or_leaking(monkeypatch):
    Connection.calls = []
    monkeypatch.setattr(s3_gateway, "PinnedHTTPSConnection", Connection)
    client = gateway()
    with pytest.raises(StorageGatewayError) as error:
        client._execute(client._signed("HEAD", "https://bucket.oss.example/key"))
    assert error.value.code is StorageErrorCode.ACCESS_DENIED
    assert Connection.calls == [("bucket.oss.example", 443, "93.184.216.34")]
    assert "key" not in str(error.value)


def test_each_request_revalidates_dns_before_connection(monkeypatch):
    answers = iter([("93.184.216.34",), ("169.254.169.254",)])
    client = gateway(lambda _h, _p: next(answers))
    Connection.calls = []
    monkeypatch.setattr(s3_gateway, "PinnedHTTPSConnection", Connection)
    request = client._signed("HEAD", "https://bucket.oss.example/key")
    with pytest.raises(StorageGatewayError):
        client._execute(request)
    with pytest.raises(StorageGatewayError):
        client._execute(request)
    assert len(Connection.calls) == 1


def test_private_http_rejects_metadata_and_public_addresses():
    for address in ("169.254.169.254", "100.100.100.200", "93.184.216.34", "0.0.0.0"):
        client = s3_gateway.SafeS3Gateway(
            provider="minio",
            internal_endpoint="http://minio:9000",
            public_endpoint="http://web",
            region="us-east-1",
            access_key_id="test",
            access_key_secret="test",
            allow_insecure_private_transport=True,
            resolver=lambda _h, _p, value=address: (value,),
        )
        with pytest.raises(PublicNetworkPolicyError):
            client._addresses("http://minio:9000")


def test_private_connection_rechecks_actual_peer(monkeypatch):
    class Socket:
        closed = False

        def getpeername(self):
            return ("169.254.169.254", 9000)

        def close(self):
            self.closed = True

    sock = Socket()
    monkeypatch.setattr(s3_gateway.socket, "create_connection", lambda *_args: sock)
    connection = s3_gateway._PinnedHTTPConnection(
        "minio",
        9000,
        verified_addresses=("172.18.0.2",),
        pinned_address="172.18.0.2",
        timeout=1,
    )
    with pytest.raises(PublicNetworkPolicyError, match="peer"):
        connection.connect()
    assert sock.closed


def test_signing_debug_never_logs_paths_or_credentials(caplog):
    with caplog.at_level(logging.DEBUG):
        gateway()._presigned(
            "PUT", "https://bucket.oss.example/sensitive-key?uploadId=sensitive-id", 300
        )
    assert "sensitive" not in caplog.text


def test_error_xml_and_oversized_ttl_are_fail_closed():
    client = gateway()
    with pytest.raises(StorageGatewayError):
        client._xml(b"<Error><Code>InvalidPart</Code></Error>")
    with pytest.raises(StorageGatewayError):
        client._xml(b"malformed")
    with pytest.raises(StorageGatewayError):
        client._presigned("GET", "https://bucket.oss.example/key", 901)
    with pytest.raises(ValueError, match="HTTPS"):
        s3_gateway.SafeS3Gateway(
            provider="aliyun_oss",
            internal_endpoint="http://oss.example",
            public_endpoint="https://oss.example",
            region="cn-hangzhou",
            access_key_id="test",
            access_key_secret="test",
        )
