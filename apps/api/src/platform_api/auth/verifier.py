import asyncio
import http.client
import json
import socket
from collections.abc import Callable
from ipaddress import ip_address
from typing import Any, Protocol
from urllib.error import URLError
from urllib.parse import urljoin, urlparse

import jwt

from platform_api.auth.identity import IdentityClaims
from platform_api.common.errors import DomainError
from platform_api.common.public_network import (
    AddressResolver,
    PublicNetworkPolicyError,
    resolve_hostname,
    validated_public_addresses,
)

SocketFactory = Callable[..., Any]
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_JWKS_REDIRECTS = 5


class TokenVerifier(Protocol):
    async def verify(self, token: str) -> IdentityClaims: ...


class UnavailableTokenVerifier:
    async def verify(self, _token: str) -> IdentityClaims:
        raise DomainError("AUTHENTICATION_REQUIRED", "身份认证服务尚未配置", 401)


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection whose TCP peer is pinned to a validated address."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        verified_addresses: tuple[str, ...],
        pinned_address: str,
        context,
        timeout: float | None = None,
        socket_factory: SocketFactory = socket.create_connection,
    ) -> None:
        super().__init__(host, port, timeout=timeout, context=context)
        self._verified_addresses = frozenset(
            ip_address(address) for address in verified_addresses
        )
        self._pinned_address = str(ip_address(pinned_address))
        self._socket_factory = socket_factory

    def connect(self) -> None:
        raw_socket = self._socket_factory(
            (self._pinned_address, self.port),
            self.timeout,
            self.source_address,
        )
        try:
            peer = ip_address(str(raw_socket.getpeername()[0]).split("%", 1)[0])
            if peer not in self._verified_addresses:
                raise PublicNetworkPolicyError(
                    "JWKS socket peer is outside the verified address set"
                )
            self.sock = self._context.wrap_socket(
                raw_socket,
                server_hostname=self.host,
            )
        except Exception:
            raw_socket.close()
            raise


def _request_target(url: str) -> str:
    parsed = urlparse(url)
    target = parsed.path or "/"
    return f"{target}?{parsed.query}" if parsed.query else target


class SafePyJWKClient(jwt.PyJWKClient):
    """PyJWT JWKS client with DNS validation and pinned HTTPS connections."""

    def __init__(
        self,
        uri: str,
        *,
        resolver: AddressResolver = resolve_hostname,
        **kwargs,
    ) -> None:
        self._resolver = resolver
        super().__init__(uri, **kwargs)

    def _open_pinned(self, url: str):
        parsed = urlparse(url)
        hostname = parsed.hostname
        if hostname is None:
            raise PublicNetworkPolicyError("JWKS URL has no hostname")
        port = parsed.port or 443
        addresses = validated_public_addresses(url, resolver=self._resolver)
        last_error: Exception | None = None
        for address in addresses:
            connection = PinnedHTTPSConnection(
                hostname,
                port,
                verified_addresses=addresses,
                pinned_address=address,
                context=self.ssl_context,
                timeout=self.timeout,
            )
            try:
                connection.request(
                    "GET",
                    _request_target(url),
                    headers={"Accept": "application/json", **self.headers},
                )
                return connection, connection.getresponse()
            except (OSError, http.client.HTTPException) as exc:
                connection.close()
                last_error = exc
        raise URLError("all validated JWKS addresses failed") from last_error

    def fetch_data(self):
        jwk_set = None
        try:
            current_url = self.uri
            for redirect_count in range(MAX_JWKS_REDIRECTS + 1):
                connection, response = self._open_pinned(current_url)
                try:
                    if response.status in REDIRECT_STATUSES:
                        location = response.getheader("Location")
                        if not location:
                            raise URLError("JWKS redirect has no Location header")
                        if redirect_count == MAX_JWKS_REDIRECTS:
                            raise URLError("too many JWKS redirects")
                        current_url = urljoin(current_url, location)
                        continue
                    if not 200 <= response.status < 300:
                        raise URLError(f"JWKS endpoint returned HTTP {response.status}")
                    jwk_set = json.load(response)
                    break
                finally:
                    response.close()
                    connection.close()
        except (PublicNetworkPolicyError, URLError, TimeoutError) as exc:
            raise jwt.PyJWKClientConnectionError(
                "Fail to fetch JWKS under the public network policy"
            ) from exc

        if self.jwk_set_cache is not None:
            self.jwk_set_cache.put(jwk_set)
        return jwk_set


class OidcTokenVerifier:
    def __init__(self, issuer: str, audience: str, jwks_client=None) -> None:
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self.jwks_client = jwks_client or SafePyJWKClient(
            f"{self.issuer}/protocol/openid-connect/certs", cache_keys=True
        )

    async def verify(self, token: str) -> IdentityClaims:
        try:
            signing_key = await asyncio.to_thread(
                self.jwks_client.get_signing_key_from_jwt, token
            )
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iat", "iss", "sub", "aud"]},
            )
            subject = str(claims["sub"]).strip()
            if not subject:
                raise ValueError("empty subject")
            email = str(claims.get("email") or "").strip().lower()
            display_name = str(
                claims.get("name")
                or claims.get("preferred_username")
                or email
                or subject
            ).strip()
            return IdentityClaims(
                issuer=self.issuer,
                subject=subject,
                email=email,
                display_name=display_name,
            )
        except DomainError:
            raise
        except Exception as exc:
            raise DomainError("AUTHENTICATION_REQUIRED", "身份凭证无效", 401) from exc
