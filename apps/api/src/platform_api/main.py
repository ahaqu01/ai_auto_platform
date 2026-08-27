from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from platform_api import __version__
from platform_api.api.auth import router as auth_router
from platform_api.api.health import router as health_router
from platform_api.api.organizations import invite_router
from platform_api.api.organizations import router as organizations_router
from platform_api.api.projects import router as projects_router
from platform_api.common.api_contract import ProblemDetails
from platform_api.common.errors import DomainError
from platform_api.settings import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="AI Auto Platform API", version=__version__, lifespan=lifespan)

    @app.middleware("http")
    async def trace_context(request: Request, call_next):
        trace_id = request.headers.get("x-request-id") or uuid4().hex
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["x-request-id"] = trace_id
        return response

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", uuid4().hex)
        problem = ProblemDetails(
            type=f"https://docs.example.com/problems/{exc.code.lower()}",
            title=exc.safe_detail,
            status=exc.http_status,
            code=exc.code,
            detail=exc.safe_detail,
            instance=request.url.path,
            traceId=trace_id,
        )
        headers = {"WWW-Authenticate": "Bearer"} if exc.http_status == 401 else None
        return JSONResponse(
            status_code=exc.http_status,
            content=problem.model_dump(),
            headers=headers,
        )

    app.include_router(auth_router)
    app.include_router(health_router)
    app.include_router(organizations_router)
    app.include_router(invite_router)
    app.include_router(projects_router)
    return app


app = create_app()
