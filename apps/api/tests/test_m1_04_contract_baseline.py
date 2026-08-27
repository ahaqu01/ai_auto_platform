import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from platform_api.api.organizations import OrganizationCreate
from platform_api.api.projects import ProjectCreate
from platform_api.common.errors import DomainError
from platform_api.main import create_app

PROBLEM_KEYS = {
    "type",
    "title",
    "status",
    "code",
    "detail",
    "instance",
    "traceId",
}


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (OrganizationCreate, {"name": "Example", "unexpected": True}),
        (
            ProjectCreate,
            {"code": "example", "name": "Example", "unexpected": True},
        ),
    ],
)
def test_request_dtos_reject_extra_fields(model, payload) -> None:
    with pytest.raises(ValidationError) as captured:
        model.model_validate(payload)
    assert captured.value.errors()[0]["type"] == "extra_forbidden"


@pytest.mark.parametrize("status_code", [401, 403, 404, 409])
def test_problem_details_shape_and_authentication_header(status_code: int) -> None:
    app = create_app()

    async def fail() -> None:
        raise DomainError("CONTRACT_ERROR", "Contract error", status_code)

    app.add_api_route("/contract-error", fail)
    response = TestClient(app).get("/contract-error")

    assert response.status_code == status_code
    assert set(response.json()) == PROBLEM_KEYS
    assert response.json()["status"] == status_code
    assert response.json()["code"] == "CONTRACT_ERROR"
    if status_code == 401:
        assert response.headers["www-authenticate"] == "Bearer"
    else:
        assert "www-authenticate" not in response.headers


def test_openapi_fixes_protected_error_responses_and_strict_dtos() -> None:
    schema = create_app().openapi()
    protected_paths = {
        "/api/v1/organizations",
        "/api/v1/organizations/{organization_id}/projects",
    }
    expected_responses = {"401", "403", "404", "409"}

    for path in protected_paths:
        for method, operation in schema["paths"][path].items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            assert expected_responses <= operation["responses"].keys()
            for status_code in expected_responses:
                response = operation["responses"][status_code]
                assert response["content"]["application/json"]["schema"] == {
                    "$ref": "#/components/schemas/ProblemDetails"
                }
            assert "WWW-Authenticate" in operation["responses"]["401"]["headers"]

    for name in ("OrganizationCreate", "ProjectCreate", "ProblemDetails"):
        assert schema["components"]["schemas"][name]["additionalProperties"] is False


def test_http_request_with_extra_field_returns_422() -> None:
    app = FastAPI()

    @app.post("/organizations")
    async def create(payload: OrganizationCreate) -> dict[str, str]:
        return {"name": payload.name}

    response = TestClient(app).post(
        "/organizations",
        json={"name": "Example", "unexpected": True},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "extra_forbidden"
