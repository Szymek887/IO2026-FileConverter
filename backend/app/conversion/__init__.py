"""Conversion module (Developer B): formats, uploads, jobs and downloads.

`create_app()` includes `router` and calls `startup(app)` / `shutdown(app)` from its lifespan.
Model modules must be imported here so their tables exist before `init_db()` runs.
"""

import asyncio

from fastapi import FastAPI

from app.conversion import models  # noqa: F401  (registers the tables)
from app.conversion.cleanup import cleanup_loop
from app.conversion.router import router
from app.conversion.worker import ThreadedJobRunner, recover_jobs
from app.core.config import settings


def startup(app: FastAPI) -> None:
    """Called on application startup (inside the event loop): start the worker threads,
    requeue jobs left over from the previous run and start the retention loop.
    A runner already set on `app.state` (tests) is kept."""
    runner = getattr(app.state, "job_runner", None)
    if runner is None:
        runner = ThreadedJobRunner(settings.worker_count)
        runner.start()
        app.state.job_runner = runner
    for job_id in recover_jobs():
        runner.submit(job_id)
    app.state.cleanup_task = asyncio.get_running_loop().create_task(
        cleanup_loop(settings.cleanup_interval_seconds), name="conversion-cleanup"
    )


def shutdown(app: FastAPI) -> None:
    """Called on application shutdown: stop the retention loop and the worker threads."""
    task = getattr(app.state, "cleanup_task", None)
    if task is not None:
        task.cancel()
        del app.state.cleanup_task
    runner = getattr(app.state, "job_runner", None)
    if isinstance(runner, ThreadedJobRunner):
        runner.stop()
        del app.state.job_runner  # a restarted lifespan gets fresh threads


__all__ = ["router", "shutdown", "startup"]
