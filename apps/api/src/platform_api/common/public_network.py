from __future__ import annotations

import socket
from collections.abc import Callable, Iterable
from ipaddress import ip_address
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request

AddressResolver = Callable[[str, int], Iterable[str]]

BLOCKED_METADATA_HOSTNAMES = {
    "instance-data",
    "metadata",
    "metadata.aliyun.com",
    "metadata.google.internal",
}


class PublicNetworkPolicyError(ValueError):
    """Raised when an outbound public URL resolves outside the public Internet."""


def is_public_hostname_candidate(hostname: str) -> bool:
    normalized = hostname.rstrip(".").lower()
    if normalized in BLOCKED_METADATA_HOSTNAMES:
        return False
    try:
        address = ip_address(normalized)
        return address.is_global and not address.is_multicast
    except ValueError:
        return True


def resolve_hostname(hostname: str, port: int) -> tuple[str, ...]:
    try:
        answers = socket.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except OSError as exc:
        raise PublicNetworkPolicyError("public hostname resolution failed") from exc
    return tuple(dict.fromkeys(answer[4][0] for answer in answers))


def validated_public_addresses(
    value: str,
    *,
    resolver: AddressResolver = resolve_hostname,
) -> str:
    try:
        parsed = urlparse(value)
        port = parsed.port or 443
    except ValueError as exc:
        raise PublicNetworkPolicyError("invalid public URL") from exc

    hostname = parsed.hostname
    if (
        parsed.scheme.lower() != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise PublicNetworkPolicyError("public URL must use HTTPS and include a host")
    if not is_public_hostname_candidate(hostname):
        raise PublicNetworkPolicyError("public URL host is not globally routable")

    try:
        addresses = tuple(resolver(hostname, port))
    except PublicNetworkPolicyError:
        raise
    except Exception as exc:
        raise PublicNetworkPolicyError("public hostname resolution failed") from exc
    if not addresses:
        raise PublicNetworkPolicyError("public hostname returned no addresses")

    try:
        all_global = all(
            ip_address(address).is_global and not ip_address(address).is_multicast
            for address in addresses
        )
    except ValueError as exc:
        raise PublicNetworkPolicyError(
            "public hostname returned an invalid address"
        ) from exc
    if not all_global:
        raise PublicNetworkPolicyError(
            "public hostname resolved outside the public Internet"
        )
    return addresses


def validate_public_url(
    value: str,
    *,
    resolver: AddressResolver = resolve_hostname,
) -> str:
    validated_public_addresses(value, resolver=resolver)
    return value


def validate_redirect_target(
    source_url: str,
    location: str,
    *,
    resolver: AddressResolver = resolve_hostname,
) -> str:
    target = urljoin(source_url, location)
    validate_public_url(target, resolver=resolver)
    return target


class PublicNetworkRedirectHandler(HTTPRedirectHandler):
    def __init__(self, resolver: AddressResolver = resolve_hostname) -> None:
        super().__init__()
        self._resolver = resolver

    def redirect_request(
        self,
        req: Request,
        fp,
        code: int,
        msg: str,
        headers,
        newurl: str,
    ) -> Request | None:
        target = validate_redirect_target(
            req.full_url,
            newurl,
            resolver=self._resolver,
        )
        return super().redirect_request(req, fp, code, msg, headers, target)
