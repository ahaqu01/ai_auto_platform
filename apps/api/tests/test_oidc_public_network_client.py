from collections.abc import Iterable
from typing import ClassVar
from urllib.request import Request

import jwt
import pytest

from platform_api.auth.verifier import PinnedHTTPSConnection, SafePyJWKClient
from platform_api.common.public_network import (
    PublicNetworkPolicyError,
    PublicNetworkRedirectHandler,
)


def resolver_returning(*addresses: str):
    def resolve(_hostname: str, _port: int) -> Iterable[str]:
        return addresses

    return resolve


def test_safe_jwks_client_rejects_sensitive_initial_dns_before_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    network_opened = False

    def unexpected_connection(*_args, **_kwargs):
        nonlocal network_opened
        network_opened = True
        raise AssertionError("network connection must not be built")

    monkeypatch.setattr(
        "platform_api.auth.verifier.PinnedHTTPSConnection",
        unexpected_connection,
    )
    client = SafePyJWKClient(
        "https://auth.example.com/realms/platform/protocol/openid-connect/certs",
        resolver=resolver_returning("169.254.169.254"),
    )

    with pytest.raises(jwt.PyJWKClientConnectionError, match="public network policy"):
        client.fetch_data()
    assert network_opened is False


def test_redirect_handler_rejects_sensitive_target_before_following() -> None:
    handler = PublicNetworkRedirectHandler(resolver_returning("169.254.169.254"))
    request = Request(
        "https://auth.example.com/realms/platform/protocol/openid-connect/certs"
    )

    with pytest.raises(PublicNetworkPolicyError):
        handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://metadata.example/latest",
        )


class FakeSocket:
    def __init__(self, peer: str) -> None:
        self.peer = peer

    def getpeername(self):
        return (self.peer, 443)

    def close(self) -> None:
        pass


class FakeTlsContext:
    def __init__(self) -> None:
        self.server_hostname: str | None = None

    def wrap_socket(self, sock, *, server_hostname: str):
        self.server_hostname = server_hostname
        return sock


def test_pinned_https_connection_rejects_peer_outside_verified_set() -> None:
    context = FakeTlsContext()
    connection = PinnedHTTPSConnection(
        "auth.example.com",
        443,
        verified_addresses=("93.184.216.34",),
        pinned_address="93.184.216.34",
        context=context,
        socket_factory=lambda *_args, **_kwargs: FakeSocket("169.254.169.254"),
    )

    with pytest.raises(PublicNetworkPolicyError, match="socket peer"):
        connection.connect()


def test_pinned_https_connection_keeps_tls_hostname_and_verified_peer() -> None:
    context = FakeTlsContext()
    connection = PinnedHTTPSConnection(
        "auth.example.com",
        443,
        verified_addresses=("93.184.216.34",),
        pinned_address="93.184.216.34",
        context=context,
        socket_factory=lambda address, *_args, **_kwargs: FakeSocket(address[0]),
    )

    connection.connect()


class FakeJwksResponse:
    def __init__(self, status: int, body: bytes, location: str | None = None) -> None:
        from io import BytesIO

        self.status = status
        self._body = BytesIO(body)
        self._location = location

    def getheader(self, name: str):
        return self._location if name.lower() == "location" else None

    def read(self, size: int = -1):
        return self._body.read(size)

    def close(self) -> None:
        pass


class FakeJwksConnection:
    responses: ClassVar[list[FakeJwksResponse]] = []
    hosts: ClassVar[list[tuple[str, str]]] = []

    def __init__(
        self, host: str, _port: int, *, pinned_address: str, **_kwargs
    ) -> None:
        self.host = host
        self.pinned_address = pinned_address

    def request(self, _method: str, _target: str, *, headers) -> None:
        self.hosts.append((self.host, self.pinned_address))
        assert headers.get("Host", True)

    def getresponse(self):
        return self.responses.pop(0)

    def close(self) -> None:
        pass


def test_safe_jwks_client_re_resolves_and_pins_every_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver_calls: list[str] = []
    addresses = {
        "auth.example.com": "93.184.216.34",
        "keys.example.com": "93.184.216.35",
    }

    def resolver(hostname: str, _port: int):
        resolver_calls.append(hostname)
        return (addresses[hostname],)

    FakeJwksConnection.hosts = []
    FakeJwksConnection.responses = [
        FakeJwksResponse(302, b"", "https://keys.example.com/jwks"),
        FakeJwksResponse(200, b'{"keys": []}'),
    ]
    monkeypatch.setattr(
        "platform_api.auth.verifier.PinnedHTTPSConnection", FakeJwksConnection
    )
    client = SafePyJWKClient("https://auth.example.com/jwks", resolver=resolver)

    assert client.fetch_data() == {"keys": []}
    assert resolver_calls == ["auth.example.com", "keys.example.com"]
    assert FakeJwksConnection.hosts == [
        ("auth.example.com", "93.184.216.34"),
        ("keys.example.com", "93.184.216.35"),
    ]
