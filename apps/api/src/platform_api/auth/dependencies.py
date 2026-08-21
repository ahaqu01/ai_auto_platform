from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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


@lru_cache
def get_token_verifier() -> TokenVerifier:
    settings = get_settings()
    if not settings.keycloak_issuer or not settings.oidc_audience:
        return UnavailableTokenVerifier()
    return OidcTokenVerifier(settings.keycloak_issuer, settings.oidc_audience)


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
) -> UserModel:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise DomainError("AUTHENTICATION_REQUIRED", "需要登录后访问", 401)
    identity = await verifier.verify(credentials.credentials)
    return await _synchronize_user(session, identity)


CurrentUser = Annotated[UserModel, Depends(get_current_user)]
