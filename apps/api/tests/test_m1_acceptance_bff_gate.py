import pytest

import platform_api.auth.bff as bff_module
from platform_api.auth.bff import BffService, MemorySessionStore
from platform_api.common.errors import DomainError
from platform_api.settings import Settings


@pytest.mark.asyncio
async def test_real_bff_service_rejects_consumed_login_state() -> None:
    service = BffService(
        Settings(
            keycloak_issuer="https://issuer.example/realms/platform",
            bff_client_secret="secret",
            _env_file=None,
        ),
        MemorySessionStore(),
        object(),
        object(),
    )
    with pytest.raises(DomainError) as error:
        await service.complete_login("code", "missing-state")
    assert error.value.code == "INVALID_LOGIN_STATE"


def test_required_bff_service_returns_configured_instance(monkeypatch) -> None:
    service = object()
    monkeypatch.setattr(bff_module, "get_optional_bff_service", lambda: service)
    assert bff_module.get_bff_service() is service
