"""Conversion module (Developer B): formats, uploads, jobs and downloads.

`create_app()` includes `router` and calls `startup(app)` / `shutdown(app)` from its lifespan.
Model modules must be imported here so their tables exist before `init_db()` runs.
"""

from fastapi import FastAPI

from app.conversion.router import router


def startup(app: FastAPI) -> None:
    """Called on application startup, inside the running event loop (start workers here)."""


def shutdown(app: FastAPI) -> None:
    """Called on application shutdown (stop workers here)."""


__all__ = ["router", "shutdown", "startup"]
