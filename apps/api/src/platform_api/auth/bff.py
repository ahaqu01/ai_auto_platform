from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import asdict, dataclass
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx
import jwt
from redis.asyncio import Redis

from platform_api.auth.identity import IdentityClaims
from platform_api.auth.verifier import TokenVerifier
from platform_api.common.errors import DomainError
from platform_api.settings import Settings, get_settings


@dataclass(frozen=True)
class LoginTransaction:
    return_to: str
    code_verifier: str
    nonce: str


@dataclass(frozen=True)
class BrowserSession:
    session_id: str
    csrf_token: str
    access_token: str
    refresh_token: str
    id_token: str
    expires_at: int
    identity: dict[str, str]


class SessionStore(Protocol):
    async def create_login(
        self, return_to: str, code_verifier: str, nonce: str
    ) -> str: ...
    async def consume_login(self, state: str) -> LoginTransaction | None: ...
    async def create_session(
        self,
        *,
        access_token: str,
        refresh_token: str,
        id_token: str,
        expires_in: int,
        identity: dict[str, str],
    ) -> BrowserSession: ...
    async def get_session(self, session_id: str) -> BrowserSession | None: ...
    async def save_session(self, session: BrowserSession) -> None: ...
    async def delete_session(self, session_id: str) -> None: ...


class MemorySessionStore:
    def __init__(self) -> None:
        self.logins: dict[str, LoginTransaction] = {}
        self.sessions: dict[str, BrowserSession] = {}

    async def create_login(self, return_to: str, code_verifier: str, nonce: str) -> str:
        state = secrets.token_urlsafe(32)
        self.logins[state] = LoginTransaction(return_to, code_verifier, nonce)
        return state

    async def consume_login(self, state: str) -> LoginTransaction | None:
        return self.logins.pop(state, None)

    async def create_session(
        self,
        *,
        access_token: str,
        refresh_token: str,
        id_token: str,
        expires_in: int,
        identity: dict[str, str],
    ) -> BrowserSession:
        session = BrowserSession(
            secrets.token_urlsafe(32),
            secrets.token_urlsafe(32),
            access_token,
            refresh_token,
            id_token,
            int(time.time()) + expires_in,
            identity,
        )
        self.sessions[session.session_id] = session
        return session

    async def get_session(self, session_id: str) -> BrowserSession | None:
        return self.sessions.get(session_id)

    async def save_session(self, session: BrowserSession) -> None:
        self.sessions[session.session_id] = session

    async def delete_session(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)


class RedisSessionStore:
    def __init__(self, redis: Redis, *, session_ttl: int) -> None:
        self.redis = redis
        self.session_ttl = session_ttl

    async def create_login(self, return_to: str, code_verifier: str, nonce: str) -> str:
        state = secrets.token_urlsafe(32)
        value = json.dumps(asdict(LoginTransaction(return_to, code_verifier, nonce)))
        await self.redis.set(f"bff:login:{state}", value, ex=300, nx=True)
        return state

    async def consume_login(self, state: str) -> LoginTransaction | None:
        value = await self.redis.getdel(f"bff:login:{state}")
        return LoginTransaction(**json.loads(value)) if value else None

    async def create_session(
        self,
        *,
        access_token: str,
        refresh_token: str,
        id_token: str,
        expires_in: int,
        identity: dict[str, str],
    ) -> BrowserSession:
        session = BrowserSession(
            secrets.token_urlsafe(32),
            secrets.token_urlsafe(32),
            access_token,
            refresh_token,
            id_token,
            int(time.time()) + expires_in,
            identity,
        )
        await self.save_session(session)
        return session

    async def get_session(self, session_id: str) -> BrowserSession | None:
        value = await self.redis.get(f"bff:session:{session_id}")
        return BrowserSession(**json.loads(value)) if value else None

    async def save_session(self, session: BrowserSession) -> None:
        await self.redis.set(
            f"bff:session:{session.session_id}",
            json.dumps(asdict(session)),
            ex=self.session_ttl,
        )

    async def delete_session(self, session_id: str) -> None:
        await self.redis.delete(f"bff:session:{session_id}")


def _identity_dict(identity: IdentityClaims) -> dict[str, str]:
    return {
        "issuer": identity.issuer,
        "subject": identity.subject,
        "email": identity.email,
        "display_name": identity.display_name,
    }


class BffService:
    def __init__(
        self,
        settings: Settings,
        store: SessionStore,
        verifier: TokenVerifier,
        id_token_verifier: TokenVerifier,
    ) -> None:
        self.settings = settings
        self.store = store
        self.verifier = verifier
        self.token_endpoint = f"{settings.keycloak_internal_issuer or settings.keycloak_issuer}/protocol/openid-connect/token"
        self.id_token_verifier = id_token_verifier
        self.logout_endpoint = f"{settings.keycloak_internal_issuer or settings.keycloak_issuer}/protocol/openid-connect/logout"

    async def authorization_url(self, return_to: str) -> str:
        return await self._oidc_url(return_to, "auth")

    async def registration_url(self, return_to: str) -> str:
        return await self._oidc_url(return_to, "registrations")

    async def _oidc_url(self, return_to: str, endpoint: str) -> str:
        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        nonce = secrets.token_urlsafe(32)
        state = await self.store.create_login(return_to, verifier, nonce)
        query = urlencode(
            {
                "client_id": self.settings.bff_client_id,
                "response_type": "code",
                "scope": "openid profile email",
                "redirect_uri": self.settings.bff_callback_url,
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{self.settings.keycloak_issuer}/protocol/openid-connect/{endpoint}?{query}"

    async def complete_login(self, code: str, state: str) -> tuple[BrowserSession, str]:
        login = await self.store.consume_login(state)
        if login is None:
            raise DomainError("INVALID_LOGIN_STATE", "登录状态无效或已使用", 400)
        tokens = await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.settings.bff_callback_url,
                "code_verifier": login.code_verifier,
            }
        )
        identity = await self.verifier.verify(str(tokens["access_token"]))
        await self.id_token_verifier.verify(str(tokens["id_token"]))
        id_claims = jwt.decode(
            str(tokens["id_token"]),
            options={"verify_signature": False, "verify_exp": False},
        )
        if not secrets.compare_digest(str(id_claims.get("nonce", "")), login.nonce):
            raise DomainError("INVALID_LOGIN_NONCE", "登录响应校验失败", 401)
        session = await self.store.create_session(
            access_token=str(tokens["access_token"]),
            refresh_token=str(tokens["refresh_token"]),
            id_token=str(tokens["id_token"]),
            expires_in=int(tokens.get("expires_in", 300)),
            identity=_identity_dict(identity),
        )
        return session, login.return_to

    async def get_session(self, session_id: str) -> BrowserSession | None:
        session = await self.store.get_session(session_id)
        if session is None or session.expires_at > int(time.time()) + 60:
            return session
        try:
            tokens = await self._token_request(
                {"grant_type": "refresh_token", "refresh_token": session.refresh_token}
            )
            identity = await self.verifier.verify(str(tokens["access_token"]))
        except (DomainError, KeyError, TypeError, ValueError):
            await self.store.delete_session(session_id)
            return None
        refreshed = BrowserSession(
            session.session_id,
            session.csrf_token,
            str(tokens["access_token"]),
            str(tokens.get("refresh_token", session.refresh_token)),
            str(tokens.get("id_token", session.id_token)),
            int(time.time()) + int(tokens.get("expires_in", 300)),
            _identity_dict(identity),
        )
        await self.store.save_session(refreshed)
        return refreshed

    async def logout(self, session_id: str) -> None:
        session = await self.store.get_session(session_id)
        if session:
            try:
                await self._post(
                    self.logout_endpoint, {"refresh_token": session.refresh_token}
                )
            except DomainError:
                pass
            finally:
                await self.store.delete_session(session_id)

    async def _token_request(self, data: dict[str, str]) -> dict[str, Any]:
        response = await self._post(self.token_endpoint, data)
        try:
            return response.json()
        except ValueError as exc:
            raise DomainError(
                "IDENTITY_PROVIDER_ERROR", "身份服务响应无效", 502
            ) from exc

    async def _post(self, url: str, data: dict[str, str]) -> httpx.Response:
        payload = {
            **data,
            "client_id": self.settings.bff_client_id,
            "client_secret": self.settings.bff_client_secret,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                response = await client.post(url, data=payload)
                response.raise_for_status()
                return response
            except httpx.HTTPError as exc:
                raise DomainError(
                    "IDENTITY_PROVIDER_UNAVAILABLE", "身份服务暂不可用", 502
                ) from exc


_service: BffService | None = None


def get_optional_bff_service() -> BffService | None:
    global _service
    if _service is None:
        settings = get_settings()
        if (
            not settings.redis_url
            or not settings.keycloak_issuer
            or not settings.bff_client_secret
        ):
            return None
        from platform_api.auth.dependencies import (
            get_bff_id_token_verifier,
            get_token_verifier,
        )

        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        _service = BffService(
            settings,
            RedisSessionStore(redis, session_ttl=settings.bff_session_ttl_seconds),
            get_token_verifier(),
            get_bff_id_token_verifier(),
        )
    return _service


def get_bff_service() -> BffService:
    service = get_optional_bff_service()
    if service is None:
        raise DomainError("AUTHENTICATION_UNAVAILABLE", "浏览器登录尚未配置", 503)
    return service
