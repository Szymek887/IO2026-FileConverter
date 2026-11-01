"""Runs conversion jobs in the background.

`POST /api/jobs` commits a queued job and hands its ID to `app.state.job_runner`.
The database is the source of truth for job state; a runner only receives IDs.
"""

from typing import Protocol


class JobRunner(Protocol):
    def submit(self, job_id: str) -> None:
        """Schedule a committed, queued job. Must return immediately."""
        ...


class ManualRunner:
    """Only records submitted job IDs; nothing is converted. Used by tests (which then
    process jobs explicitly) and as the app's runner until the worker threads exist (B8)."""

    def __init__(self) -> None:
        self.submitted: list[str] = []

    def submit(self, job_id: str) -> None:
        self.submitted.append(job_id)
