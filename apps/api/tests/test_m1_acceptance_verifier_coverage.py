from types import SimpleNamespace

import pytest

import platform_api.auth.verifier as verifier_module
from platform_api.auth.verifier import OidcTokenVerifier
from platform_api.common.errors import DomainError


class FakeJwks:
    def get_signing_key_from_jwt(self, _token):
        return SimpleNamespace(key="key")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("claims", "display_name"),
    [
        ({"sub": "subject", "preferred_username": "preferred"}, "preferred"),
        ({"sub": "subject", "email": "USER@EXAMPLE.COM"}, "user@example.com"),
        ({"sub": "subject"}, "subject"),
    ],
)
async def test_oidc_display_name_fallbacks(monkeypatch, claims, display_name) -> None:
    monkeypatch.setattr(verifier_module.jwt, "decode", lambda *_args, **_kwargs: claims)
    identity = await OidcTokenVerifier("https://issuer", "api", FakeJwks()).verify(
        "token"
    )
    assert identity.display_name == display_name


@pytest.mark.asyncio
async def test_oidc_empty_subject_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        verifier_module.jwt,
        "decode",
        lambda *_args, **_kwargs: {"sub": "   ", "name": "Name"},
    )
    with pytest.raises(DomainError) as error:
        await OidcTokenVerifier("https://issuer", "api", FakeJwks()).verify("token")
    assert error.value.code == "AUTHENTICATION_REQUIRED"
