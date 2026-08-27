import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import RedirectResponse

from platform_api.auth.bff import BffService, get_bff_service
from platform_api.common.api_contract import AUTH_SESSION_ERROR_RESPONSES
from platform_api.common.errors import DomainError
from platform_api.settings import Settings, get_settings

router = APIRouter(prefix="/auth", tags=["authentication"])
Service = Annotated[BffService, Depends(get_bff_service)]
Config = Annotated[Settings, Depends(get_settings)]


def _return_target(value: str) -> str:
    return value if value.startswith("/") and not value.startswith("//") else "/"


def _set_cookie(response: Response, session_id: str, settings: Settings) -> None:
    response.set_cookie(
        settings.bff_cookie_name,
        session_id,
        max_age=settings.bff_session_ttl_seconds,
        httponly=True,
        secure=settings.app_env in {"staging", "production"},
        samesite="lax",
        path="/",
    )


@router.get("/login", status_code=303)
async def login(service: Service, return_to: str = Query("/")) -> RedirectResponse:
    return RedirectResponse(
        await service.authorization_url(_return_target(return_to)), status_code=303
    )


@router.get("/callback", status_code=303)
async def callback(
    code: str, state: str, service: Service, settings: Config
) -> RedirectResponse:
    session, return_to = await service.complete_login(code, state)
    response = RedirectResponse(_return_target(return_to), status_code=303)
    _set_cookie(response, session.session_id, settings)
    return response


@router.get("/session")
async def browser_session(
    request: Request, service: Service, settings: Config
) -> dict[str, object]:
    session_id = request.cookies.get(settings.bff_cookie_name)
    if not session_id:
        return {"authenticated": False}
    session = await service.get_session(session_id)
    if session is None:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "csrfToken": session.csrf_token,
        "user": {
            "subject": session.identity["subject"],
            "email": session.identity.get("email", ""),
            "displayName": session.identity.get("display_name", ""),
        },
    }


@router.post(
    "/logout",
    status_code=204,
    responses=AUTH_SESSION_ERROR_RESPONSES,
)
async def logout(
    request: Request,
    response: Response,
    service: Service,
    settings: Config,
    origin: Annotated[str | None, Header()] = None,
    csrf_token: Annotated[str | None, Header(alias="x-csrf-token")] = None,
) -> None:
    session_id = request.cookies.get(settings.bff_cookie_name)
    if not session_id:
        raise DomainError("AUTHENTICATION_REQUIRED", "需要登录后访问", 401)
    session = await service.get_session(session_id)
    if session is None:
        raise DomainError("AUTHENTICATION_REQUIRED", "会话已失效", 401)
    if (
        origin != settings.bff_public_origin
        or not csrf_token
        or not secrets.compare_digest(csrf_token, session.csrf_token)
    ):
        raise DomainError("CSRF_REJECTED", "请求来源或 CSRF 校验失败", 403)
    await service.logout(session_id)
    response.delete_cookie(
        settings.bff_cookie_name, path="/", httponly=True, samesite="lax"
    )
