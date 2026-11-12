from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.api.v1.internal import router as internal_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(internal_router, prefix="/api/v1")
    return app


app = create_app()
