"""Conversion module (Developer B): formats, uploads, jobs and downloads.

`create_app()` includes `router` and calls `startup(app)` / `shutdown(app)` from its lifespan.
Model modules must be imported here so their tables exist before `init_db()` runs.
"""

from fastapi import FastAPI

from app.conversion import models  # noqa: F401  (registers the tables)
from app.conversion.router import router
from app.conversion.worker import ManualRunner


def startup(app: FastAPI) -> None:
    """Called on application startup, inside the running event loop (start workers here)."""
    # Jobs stay queued until the worker threads exist (B8).
    app.state.job_runner = ManualRunner()


def shutdown(app: FastAPI) -> None:
    """Called on application shutdown (stop workers here)."""


__all__ = ["router", "shutdown", "startup"]
