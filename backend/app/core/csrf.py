"""CSRF protection: double-submit cookie.

The browser keeps a random, JS-readable cookie `vid_csrf`; the frontend copies it into the
`X-CSRF-Token` header for every state-changing request. A foreign site can make the browser send
cookies, but it can neither read our cookie nor set custom headers without CORS (which we don't
enable). Requests authenticated with an Authorization header don't use cookies at all, so they
are exempt (Swagger, API clients).
"""

import secrets
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.core.config import get_settings

CSRF_COOKIE = "vid_csrf"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# OAuth2 token endpoint sets no cookies, so a forged request gains nothing.
EXEMPT_PATHS = {"/api/v1/auth/token"}


def _origin_ok(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True  # same-origin fetches from older browsers / non-browser clients
    host = request.headers.get("host", "")
    return origin.split("://", 1)[-1] == host


async def csrf_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    path = request.url.path
    needs_check = (
        request.method not in SAFE_METHODS
        and path.startswith("/api/")
        and path not in EXEMPT_PATHS
        and not request.headers.get("authorization", "").lower().startswith("bearer ")
    )
    if needs_check:
        cookie = request.cookies.get(CSRF_COOKIE, "")
        header = request.headers.get(CSRF_HEADER, "")
        valid = bool(cookie) and bool(header) and secrets.compare_digest(cookie, header)
        if not valid or not _origin_ok(request):
            return JSONResponse(
                {"error": {"code": "csrf_failed", "message": "CSRF token missing or invalid"}},
                status_code=403,
            )

    response = await call_next(request)
    if CSRF_COOKIE not in request.cookies and path.startswith("/api/"):
        response.set_cookie(
            CSRF_COOKIE,
            secrets.token_urlsafe(32),
            httponly=False,  # the frontend must read it
            secure=get_settings().cookie_secure,
            samesite="strict",
            path="/",
        )
    return response
