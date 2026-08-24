import asyncio
import json
import urllib.request
from typing import Protocol
from urllib.error import HTTPError, URLError

import jwt

from platform_api.auth.identity import IdentityClaims
from platform_api.common.errors import DomainError
from platform_api.common.public_network import (
    AddressResolver,
    PublicNetworkPolicyError,
    PublicNetworkRedirectHandler,
    resolve_hostname,
    validate_public_url,
)


class TokenVerifier(Protocol):
    async def verify(self, token: str) -> IdentityClaims: ...


class UnavailableTokenVerifier:
    async def verify(self, _token: str) -> IdentityClaims:
        raise DomainError("AUTHENTICATION_REQUIRED", "身份认证服务尚未配置", 401)


class SafePyJWKClient(jwt.PyJWKClient):
    """PyJWT JWKS client with public DNS and redirect validation."""

    def __init__(
        self,
        uri: str,
        *,
        resolver: AddressResolver = resolve_hostname,
        **kwargs,
    ) -> None:
        self._resolver = resolver
        super().__init__(uri, **kwargs)

    def fetch_data(self):
        jwk_set = None
        try:
            validate_public_url(self.uri, resolver=self._resolver)
            request = urllib.request.Request(url=self.uri, headers=self.headers)
            opener = urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=self.ssl_context),
                PublicNetworkRedirectHandler(self._resolver),
            )
            with opener.open(request, timeout=self.timeout) as response:
                jwk_set = json.load(response)
        except (PublicNetworkPolicyError, URLError, TimeoutError) as exc:
            if isinstance(exc, HTTPError):
                exc.close()
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
