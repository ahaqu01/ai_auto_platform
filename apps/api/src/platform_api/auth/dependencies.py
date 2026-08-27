import secrets
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_api.auth.bff import BffService, get_optional_bff_service
from platform_api.auth.identity import IdentityClaims
from platform_api.auth.verifier import (
    OidcTokenVerifier,
    TokenVerifier,
    UnavailableTokenVerifier,
)
from platform_api.common.errors import DomainError
from platform_api.db.models import UserModel
from platform_api.db.session import get_session
from platform_api.settings import get_settings

bearer_scheme = HTTPBearer(auto_error=False)


def _oidc_verifier(audience: str | None) -> TokenVerifier:
    settings = get_settings()
    if not settings.keycloak_issuer or not audience:
        return UnavailableTokenVerifier()
    if settings.app_env == "local" and settings.keycloak_internal_issuer:
        jwks = jwt.PyJWKClient(
            f"{settings.keycloak_internal_issuer}/protocol/openid-connect/certs",
            cache_keys=True,
        )
        return OidcTokenVerifier(settings.keycloak_issuer, audience, jwks)
    return OidcTokenVerifier(settings.keycloak_issuer, audience)


@lru_cache
def get_token_verifier() -> TokenVerifier:
    return _oidc_verifier(get_settings().oidc_audience)


@lru_cache
def get_bff_id_token_verifier() -> TokenVerifier:
    return _oidc_verifier(get_settings().bff_client_id)


async def _synchronize_user(
    session: AsyncSession, identity: IdentityClaims
) -> UserModel:
    user = await session.scalar(
        select(UserModel).where(
            UserModel.external_issuer == identity.issuer,
            UserModel.external_subject == identity.subject,
        )
    )
    if user is None:
        user = UserModel(
            external_issuer=identity.issuer,
            external_subject=identity.subject,
            email=identity.email or f"{identity.subject}@identity.invalid",
            display_name=identity.display_name,
        )
        session.add(user)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise DomainError("IDENTITY_CONFLICT", "身份资料冲突", 409) from exc
        await session.refresh(user)
        return user

    changed = False
    if identity.email and user.email != identity.email:
        user.email = identity.email
        changed = True
    if identity.display_name and user.display_name != identity.display_name:
        user.display_name = identity.display_name
        changed = True
    if changed:
        await session.commit()
        await session.refresh(user)
    return user


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
    session: Annotated[AsyncSession, Depends(get_session)],
    request: Request,
    bff: Annotated[BffService | None, Depends(get_optional_bff_service)],
) -> UserModel:
    if credentials is not None and credentials.scheme.lower() == "bearer":
        identity = await verifier.verify(credentials.credentials)
        return await _synchronize_user(session, identity)

    settings = get_settings()
    session_id = request.cookies.get(settings.bff_cookie_name)
    browser_session = await bff.get_session(session_id) if session_id and bff else None
    if browser_session is None:
        raise DomainError("AUTHENTICATION_REQUIRED", "需要登录后访问", 401)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        csrf = request.headers.get("x-csrf-token")
        if (
            origin != settings.bff_public_origin
            or not csrf
            or not secrets.compare_digest(csrf, browser_session.csrf_token)
        ):
            raise DomainError("CSRF_REJECTED", "请求来源或 CSRF 校验失败", 403)
    identity = await verifier.verify(browser_session.access_token)
    return await _synchronize_user(session, identity)


CurrentUser = Annotated[UserModel, Depends(get_current_user)]
