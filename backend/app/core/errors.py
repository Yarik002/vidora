import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("vidora")


class AppError(Exception):
    """Business error with a stable machine-readable code. Raised by services."""

    status_code = 400
    code = "bad_request"

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        self.message = message or self.default_message
        if code:
            self.code = code
        super().__init__(self.message)

    default_message = "Bad request"


class NotFound(AppError):
    status_code = 404
    code = "not_found"
    default_message = "Not found"


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"
    default_message = "Authentication required"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"
    default_message = "Not allowed"


class Conflict(AppError):
    status_code = 409
    code = "conflict"
    default_message = "Conflict"


class TooManyRequests(AppError):
    status_code = 429
    code = "rate_limited"
    default_message = "Too many requests, try again later"


def _body(code: str, message: str, details: object | None = None) -> dict:
    error: dict = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        headers = {"Retry-After": "60"} if isinstance(exc, TooManyRequests) else None
        return JSONResponse(_body(exc.code, exc.message), status_code=exc.status_code, headers=headers)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            _body("http_error", str(exc.detail)), status_code=exc.status_code, headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse(_body("validation_error", "Invalid request", details), status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Full traceback goes to logs only; the client never sees internals.
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(_body("internal_error", "Internal server error"), status_code=500)
