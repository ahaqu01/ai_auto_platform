from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from platform_api.auth.bff import MemorySessionStore, get_bff_service
from platform_api.common.errors import DomainError
from platform_api.main import create_app


class FakeBffService:
    def __init__(self) -> None:
        self.store = MemorySessionStore()
        self.revoked: list[str] = []

    async def authorization_url(self, return_to: str) -> str:
        state = await self.store.create_login(return_to, "verifier", "nonce")
        return f"https://id.example/authorize?state={state}&code_challenge=challenge&code_challenge_method=S256"

    async def complete_login(self, code: str, state: str):
        login = await self.store.consume_login(state)
        if code != "code" or login is None:
            raise DomainError("INVALID_LOGIN_STATE", "登录状态无效或已使用", 400)
        return await self.store.create_session(
            access_token="access",
            refresh_token="refresh",
            id_token="id",
            expires_in=300,
            identity={
                "subject": "subject-1",
                "email": "user@example.com",
                "display_name": "User",
            },
        ), login.return_to

    async def logout(self, session_id: str) -> None:
        session = await self.store.get_session(session_id)
        if session:
            self.revoked.append(session.refresh_token)
        await self.store.delete_session(session_id)

    async def get_session(self, session_id: str):
        return await self.store.get_session(session_id)


def client():
    app = create_app()
    service = FakeBffService()
    app.dependency_overrides[get_bff_service] = lambda: service
    return TestClient(app), service


def test_login_uses_code_pkce_and_rejects_external_return_target() -> None:
    api, _ = client()
    response = api.get(
        "/auth/login?return_to=https://evil.example", follow_redirects=False
    )
    assert response.status_code == 303
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"]


def test_callback_creates_http_only_session_and_state_is_one_time() -> None:
    api, _ = client()
    login = api.get("/auth/login?return_to=/console", follow_redirects=False)
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    response = api.get(
        f"/auth/callback?code=code&state={state}", follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/console"
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    replay = api.get(f"/auth/callback?code=code&state={state}", follow_redirects=False)
    assert replay.status_code == 400


def test_session_and_logout_enforce_origin_and_csrf() -> None:
    api, service = client()
    login = api.get("/auth/login", follow_redirects=False)
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    api.get(f"/auth/callback?code=code&state={state}", follow_redirects=False)
    session = api.get("/auth/session")
    assert session.status_code == 200
    csrf = session.json()["csrfToken"]
    denied = api.post("/auth/logout")
    assert denied.status_code == 403
    accepted = api.post(
        "/auth/logout",
        headers={"origin": "http://testserver", "x-csrf-token": csrf},
    )
    assert accepted.status_code == 204
    assert service.revoked == ["refresh"]
    assert "Max-Age=0" in accepted.headers["set-cookie"]
