from fastapi import APIRouter
from pydantic import BaseModel

from platform_api.settings import get_settings

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/live", response_model=HealthResponse)
async def live() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
    )


@router.get("/ready", response_model=HealthResponse)
async def ready() -> HealthResponse:
    # Dependency probes will be added with database/Redis/Temporal adapters.
    return await live()

