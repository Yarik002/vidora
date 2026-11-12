import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import (
    auth,
    channels,
    comments,
    health,
    internal,
    me,
    moderation,
    playlists,
    search,
    uploads,
    videos,
)
from app.core.config import get_settings
from app.core.csrf import csrf_middleware
from app.core.errors import register_error_handlers
from app.db.session import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

DESCRIPTION = """
Vidora: a YouTube-like video platform (test assignment).

**Auth for Swagger:** press *Authorize* and log in with username/email and password
(OAuth2 password flow, bearer token). Browsers use httpOnly cookies + CSRF header instead.
"""


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="1.0.0",
        description=DESCRIPTION,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    register_error_handlers(app)
    app.middleware("http")(csrf_middleware)

    api_prefix = "/api/v1"
    for router in (
        health.router,
        internal.router,
        auth.router,
        videos.router,
        uploads.router,
        comments.router,
        channels.router,
        playlists.router,
        me.router,
        search.router,
        moderation.reports_router,
        moderation.router,
        moderation.admin_router,
    ):
        app.include_router(router, prefix=api_prefix)
    return app


app = create_app()
