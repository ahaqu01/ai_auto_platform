from fastapi.testclient import TestClient

from platform_api.auth.dependencies import get_token_verifier
from platform_api.main import create_app


def test_unconfigured_oidc_returns_stable_401() -> None:
    get_token_verifier.cache_clear()
    response = TestClient(create_app()).get(
        "/api/v1/organizations",
        headers={"Authorization": "Bearer any-token"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"
