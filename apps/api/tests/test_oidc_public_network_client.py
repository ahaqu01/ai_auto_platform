from collections.abc import Iterable
from urllib.request import Request

import jwt
import pytest

from platform_api.auth.verifier import SafePyJWKClient
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

    def unexpected_build_opener(*_handlers):
        nonlocal network_opened
        network_opened = True
        raise AssertionError("network opener must not be built")

    monkeypatch.setattr(
        "platform_api.auth.verifier.urllib.request.build_opener",
        unexpected_build_opener,
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
