import uuid
from collections.abc import Callable

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import Forbidden, TooManyRequests, Unauthorized
from app.core.redis import rate_limit_hit
from app.core.security import decode_access_token
from app.db.session import get_session
from app.models import Role, User
from app.repositories import users as users_repo
from app.services.auth_service import ClientInfo
from app.services.storage import safe_host

ACCESS_COOKIE = "__Host-vid_at"
REFRESH_COOKIE = "vid_rt"
CSRF_COOKIE = "vid_csrf"

# Swagger "Authorize" button uses this endpoint; browsers use cookies instead.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


def client_info(request: Request) -> ClientInfo:
    return ClientInfo(
        ip=request.client.host if request.client else None, user_agent=request.headers.get("user-agent")
    )


def public_host(request: Request) -> str:
    """Host the browser used; presigned storage URLs are signed for it."""
    return safe_host(request.headers.get("host"))


async def current_user_optional(
    request: Request,
    bearer: str | None = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    # If an Authorization header is present, cookies are ignored entirely:
    # that is what makes skipping CSRF checks for bearer requests safe.
    token = bearer if bearer else request.cookies.get(ACCESS_COOKIE)
    if not token:
        return None
    payload = decode_access_token(token)
    if payload is None:
        return None
    try:
        user_id, session_id = uuid.UUID(payload["sub"]), uuid.UUID(payload["sid"])
    except (ValueError, KeyError):
        return None
    return await users_repo.get_active_user_for_session(session, user_id, session_id)


async def current_user(user: User | None = Depends(current_user_optional)) -> User:
    if user is None:
        raise Unauthorized()
    return user


def require_roles(*roles: Role) -> Callable:
    async def checker(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise Forbidden("Insufficient role", code="insufficient_role")
        return user

    return checker


require_moderator = require_roles(Role.MODERATOR, Role.ADMIN)
require_admin = require_roles(Role.ADMIN)


def rate_limited(name: str, limit_attr: str) -> Callable:
    """Per-IP fixed-window limit for sensitive endpoints (login, register)."""

    async def checker(request: Request) -> None:
        settings = get_settings()
        ip = request.client.host if request.client else "unknown"
        if not await rate_limit_hit(
            f"{name}:{ip}", getattr(settings, limit_attr), settings.rate_limit_window_sec
        ):
            raise TooManyRequests()

    return checker
