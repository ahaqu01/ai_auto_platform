from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from platform_api.db.session import engine
from platform_api.settings import get_settings

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ReadinessResponse(HealthResponse):
    checks: dict[str, str]


async def probe_database() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


def get_database_probe() -> Callable[[], Awaitable[None]]:
    return probe_database


@router.get("/live", response_model=HealthResponse)
async def live() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
    )


@router.get("/ready", response_model=ReadinessResponse)
async def ready(
    database_probe: Callable[[], Awaitable[None]] = Depends(get_database_probe),
) -> ReadinessResponse:
    settings = get_settings()
    try:
        await database_probe()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "checks": {"database": "failed"}},
        ) from exc
    return ReadinessResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        checks={"database": "ok"},
    )
