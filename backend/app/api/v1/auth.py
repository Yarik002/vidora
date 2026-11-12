from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    client_info,
    current_user,
    current_user_optional,
    rate_limited,
)
from app.core.config import get_settings
from app.core.errors import Unauthorized
from app.db.session import get_session
from app.models import User
from app.schemas.auth import LoginIn, MeOut, RegisterIn, TokenOut
from app.schemas.common import Message
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_PATH = "/api/v1/auth"


def _set_auth_cookies(response: Response, tokens: auth_service.Tokens) -> None:
    s = get_settings()
    response.set_cookie(
        ACCESS_COOKIE,
        tokens.access,
        max_age=s.access_ttl_minutes * 60,
        httponly=True,
        secure=True,  # __Host- prefix requires Secure and Path=/
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh,
        max_age=s.refresh_ttl_days * 86400,
        httponly=True,
        secure=s.cookie_secure,
        samesite="strict",
        path=REFRESH_PATH,  # sent only to /api/v1/auth/*, never to the rest of the API
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH, secure=True, httponly=True, samesite="strict")


@router.post(
    "/register",
    response_model=MeOut,
    status_code=201,
    dependencies=[Depends(rate_limited("register", "register_rate_limit"))],
)
async def register(
    data: RegisterIn, request: Request, response: Response, session: AsyncSession = Depends(get_session)
) -> User:
    tokens = await auth_service.register(session, data, client_info(request))
    _set_auth_cookies(response, tokens)
    return tokens.user


@router.post(
    "/login", response_model=MeOut, dependencies=[Depends(rate_limited("login", "login_rate_limit"))]
)
async def login(
    data: LoginIn, request: Request, response: Response, session: AsyncSession = Depends(get_session)
) -> User:
    tokens = await auth_service.login(session, data.login, data.password, client_info(request))
    _set_auth_cookies(response, tokens)
    return tokens.user


@router.post(
    "/token", response_model=TokenOut, dependencies=[Depends(rate_limited("login", "login_rate_limit"))]
)
async def token(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
) -> TokenOut:
    """OAuth2 password flow for Swagger UI ("Authorize") and API clients. Returns a bearer token
    and sets no cookies; `username` accepts email or username."""
    access = await auth_service.issue_bearer(session, form.username, form.password, client_info(request))
    return TokenOut(access_token=access)


@router.post(
    "/refresh", response_model=MeOut, responses={401: {"description": "Refresh failed, cookies cleared"}}
)
async def refresh(
    request: Request, response: Response, session: AsyncSession = Depends(get_session)
) -> User | JSONResponse:
    try:
        tokens = await auth_service.refresh(
            session, request.cookies.get(REFRESH_COOKIE), client_info(request)
        )
    except Unauthorized as exc:
        failed = JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=401)
        _clear_auth_cookies(failed)
        return failed
    _set_auth_cookies(response, tokens)
    return tokens.user


@router.post("/logout", response_model=Message)
async def logout(
    request: Request,
    response: Response,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> Message:
    await auth_service.logout(session, request.cookies.get(REFRESH_COOKIE), user)
    _clear_auth_cookies(response)
    return Message()


@router.get("/me", response_model=MeOut)
async def me(user: User = Depends(current_user)) -> User:
    return user
