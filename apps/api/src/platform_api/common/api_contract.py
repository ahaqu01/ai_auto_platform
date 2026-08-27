from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StrictOrmModel(StrictModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ProblemDetails(StrictModel):
    type: str
    title: str
    status: int
    code: str
    detail: str
    instance: str
    traceId: str


def _problem_response(description: str) -> dict[str, object]:
    return {"model": ProblemDetails, "description": description}


PROTECTED_ERROR_RESPONSES: dict[int, dict[str, object]] = {
    401: {
        **_problem_response("Authentication required"),
        "headers": {
            "WWW-Authenticate": {
                "description": "Bearer authentication challenge",
                "schema": {"type": "string", "example": "Bearer"},
            }
        },
    },
    403: _problem_response("Authenticated but not authorized"),
    404: _problem_response("Resource not found or hidden by tenant boundary"),
    409: _problem_response("Request conflicts with current resource state"),
}

AUTH_SESSION_ERROR_RESPONSES: dict[int, dict[str, object]] = {
    status: response
    for status, response in PROTECTED_ERROR_RESPONSES.items()
    if status in {401, 403}
}
