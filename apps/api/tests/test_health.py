
from fastapi.testclient import TestClient

from platform_api.api.health import get_database_probe
from platform_api.main import app


def test_live_health_does_not_require_dependencies() -> None:
    response = TestClient(app).get("/health/live")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "ai-auto-platform",
        "version": "0.1.0",
    }
    assert response.headers["x-request-id"]


def test_ready_health_reports_database_success() -> None:
    async def successful_probe() -> None:
        return None

    app.dependency_overrides[get_database_probe] = lambda: successful_probe
    try:
        response = TestClient(app).get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "ai-auto-platform",
        "version": "0.1.0",
        "checks": {"database": "ok"},
    }


def test_ready_health_fails_when_database_is_unavailable() -> None:
    async def failed_probe() -> None:
        raise OSError("database unavailable")

    app.dependency_overrides[get_database_probe] = lambda: failed_probe
    try:
        response = TestClient(app).get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "status": "not_ready",
            "checks": {"database": "failed"},
        }
    }
