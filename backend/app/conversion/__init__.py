"""Conversion module (Developer B): formats, uploads, jobs and downloads.

`create_app()` includes `router` and calls `startup(app)` / `shutdown(app)` from its lifespan.
Model modules must be imported here so their tables exist before `init_db()` runs.
"""

from fastapi import FastAPI

from app.conversion import models  # noqa: F401  (registers the tables)
from app.conversion.router import router
from app.conversion.worker import ThreadedJobRunner, recover_jobs
from app.core.config import settings


def startup(app: FastAPI) -> None:
    """Called on application startup: start the worker threads and requeue jobs left over
    from the previous run. A runner already set on `app.state` (tests) is kept."""
    runner = getattr(app.state, "job_runner", None)
    if runner is None:
        runner = ThreadedJobRunner(settings.worker_count)
        runner.start()
        app.state.job_runner = runner
    for job_id in recover_jobs():
        runner.submit(job_id)


def shutdown(app: FastAPI) -> None:
    """Called on application shutdown: stop the worker threads."""
    runner = getattr(app.state, "job_runner", None)
    if isinstance(runner, ThreadedJobRunner):
        runner.stop()
        del app.state.job_runner  # a restarted lifespan gets fresh threads


__all__ = ["router", "shutdown", "startup"]
