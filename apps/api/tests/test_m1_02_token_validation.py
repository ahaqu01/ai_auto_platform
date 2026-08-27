import jwt
import pytest

from platform_api.auth.bff import BffService, MemorySessionStore
from platform_api.auth.identity import IdentityClaims
from platform_api.common.errors import DomainError
from platform_api.settings import Settings


class RecordingVerifier:
    def __init__(self) -> None:
        self.tokens: list[str] = []

    async def verify(self, token: str) -> IdentityClaims:
        self.tokens.append(token)
        return IdentityClaims(
            "https://issuer.example/realms/platform",
            "subject",
            "user@example.com",
            "User",
        )


class TokenResponseBff(BffService):
    def __init__(self, *args, nonce: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.nonce = nonce

    async def _token_request(self, data: dict[str, str]):
        return {
            "access_token": "signed-access-token",
            "refresh_token": "refresh-token",
            "id_token": jwt.encode(
                {"nonce": self.nonce},
                "test-only-key-with-32-bytes-minimum",
                algorithm="HS256",
            ),
            "expires_in": 300,
        }


@pytest.mark.asyncio
async def test_callback_verifies_access_and_id_tokens_before_session_creation() -> None:
    store = MemorySessionStore()
    access = RecordingVerifier()
    identity = RecordingVerifier()
    service = TokenResponseBff(
        Settings(
            keycloak_issuer="https://issuer.example/realms/platform",
            bff_client_secret="secret",
            _env_file=None,
        ),
        store,
        access,
        identity,
        nonce="expected",
    )
    state = await store.create_login("/", "verifier", "expected")
    session, _ = await service.complete_login("code", state)
    assert access.tokens == ["signed-access-token"]
    assert len(identity.tokens) == 1
    assert session.identity["subject"] == "subject"


@pytest.mark.asyncio
async def test_callback_rejects_nonce_after_id_token_verification() -> None:
    store = MemorySessionStore()
    identity = RecordingVerifier()
    service = TokenResponseBff(
        Settings(
            keycloak_issuer="https://issuer.example/realms/platform",
            bff_client_secret="secret",
            _env_file=None,
        ),
        store,
        RecordingVerifier(),
        identity,
        nonce="wrong",
    )
    state = await store.create_login("/", "verifier", "expected")
    with pytest.raises(DomainError, match="登录响应校验失败"):
        await service.complete_login("code", state)
    assert len(identity.tokens) == 1
