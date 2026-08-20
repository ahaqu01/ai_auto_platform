from fastapi.testclient import TestClient

from platform_api.main import app


def test_live_health() -> None:
    response = TestClient(app).get("/health/live")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "ai-auto-platform",
        "version": "0.1.0",
    }
    assert response.headers["x-request-id"]

