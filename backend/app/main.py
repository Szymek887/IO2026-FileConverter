import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import conversion
from app.auth.router import router as auth_router
from app.core.config import settings
from app.core.db import init_db
from app.core.errors import register_exception_handlers
from app.health.router import router as health_router


def configure_logging() -> None:
    """Show INFO logs of our own `app.*` loggers next to uvicorn's (uvicorn only configures
    its own loggers)."""
    app_logger = logging.getLogger("app")
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s - %(message)s"))
        app_logger.addHandler(handler)
        app_logger.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    conversion.startup(app)
    try:
        yield
    finally:
        conversion.shutdown(app)


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Konwerter plików multimedialnych", version="1.0.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)

    app.include_router(auth_router)
    app.include_router(health_router)
    app.include_router(conversion.router)
    return app


app = create_app()
