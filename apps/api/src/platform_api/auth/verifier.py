import asyncio
from typing import Protocol

import jwt

from platform_api.auth.identity import IdentityClaims
from platform_api.common.errors import DomainError


class TokenVerifier(Protocol):
    async def verify(self, token: str) -> IdentityClaims: ...


class UnavailableTokenVerifier:
    async def verify(self, _token: str) -> IdentityClaims:
        raise DomainError("AUTHENTICATION_REQUIRED", "身份认证服务尚未配置", 401)


class OidcTokenVerifier:
    def __init__(self, issuer: str, audience: str, jwks_client=None) -> None:
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self.jwks_client = jwks_client or jwt.PyJWKClient(
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
