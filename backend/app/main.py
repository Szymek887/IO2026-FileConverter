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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    conversion.startup(app)
    try:
        yield
    finally:
        conversion.shutdown(app)


def create_app() -> FastAPI:
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
