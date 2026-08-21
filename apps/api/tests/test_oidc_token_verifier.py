from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from platform_api.auth.verifier import OidcTokenVerifier
from platform_api.common.errors import DomainError

ISSUER = "http://keycloak.test/realms/ai-platform"
AUDIENCE = "ai-platform-api"


class SigningKey:
    def __init__(self, key) -> None:
        self.key = key


class StaticJwksClient:
    def __init__(self, public_key) -> None:
        self.public_key = public_key

    def get_signing_key_from_jwt(self, _token: str) -> SigningKey:
        return SigningKey(self.public_key)


@pytest.fixture
def key_pair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


def token(private_key, **overrides) -> str:
    now = datetime.now(UTC)
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "user-123",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "email": "USER@example.com",
        "name": "Test User",
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test"})


@pytest.mark.asyncio
async def test_valid_rs256_token_returns_normalized_identity(key_pair) -> None:
    private, public = key_pair
    verifier = OidcTokenVerifier(ISSUER, AUDIENCE, StaticJwksClient(public))
    identity = await verifier.verify(token(private))
    assert identity.subject == "user-123"
    assert identity.email == "user@example.com"
    assert identity.display_name == "Test User"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},
        {"iss": "http://wrong-issuer"},
        {"aud": "wrong-audience"},
        {"sub": ""},
    ],
)
async def test_invalid_claims_return_stable_authentication_error(
    key_pair, overrides
) -> None:
    private, public = key_pair
    verifier = OidcTokenVerifier(ISSUER, AUDIENCE, StaticJwksClient(public))
    with pytest.raises(DomainError) as error:
        await verifier.verify(token(private, **overrides))
    assert error.value.code == "AUTHENTICATION_REQUIRED"
    assert error.value.http_status == 401
