"""Runs conversion jobs in the background.

`POST /api/jobs` commits a queued job and hands its ID to `app.state.job_runner`.
The database is the source of truth for job state; a runner only receives IDs, so after a
restart `recover_jobs()` can rebuild the queue from the database.

A job is all-or-nothing: files are converted in upload order, the first failure ends the
job with an error naming that file and no outputs are kept. Uploads are deleted when the
job finishes either way.
"""

import logging
import queue
import threading
from typing import Protocol

from sqlalchemy import select, update

from app.conversion import storage
from app.conversion.converters import ConversionError, convert
from app.conversion.models import Job, JobStatus, OutputFile, Result, ResultStatus
from app.core import messages
from app.core.clock import now
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.errors import ErrorCode

logger = logging.getLogger(__name__)

STOP_TIMEOUT_SECONDS = 5


class JobRunner(Protocol):
    def submit(self, job_id: str) -> None:
        """Schedule a committed, queued job. Must return immediately."""
        ...

    def stop(self) -> None:
        """Stop accepting work (called on application shutdown)."""
        ...


class ManualRunner:
    """Only records submitted job IDs; nothing is converted. Tests use it and then run
    `process_job()` themselves."""

    def __init__(self) -> None:
        self.submitted: list[str] = []

    def submit(self, job_id: str) -> None:
        self.submitted.append(job_id)

    def stop(self) -> None:
        pass


class ThreadedJobRunner:
    """`worker_count` daemon threads taking job IDs from an in-memory queue."""

    def __init__(self, worker_count: int) -> None:
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._threads = [
            threading.Thread(target=self._work, name=f"conversion-worker-{i}", daemon=True)
            for i in range(worker_count)
        ]

    def start(self) -> None:
        for thread in self._threads:
            thread.start()

    def submit(self, job_id: str) -> None:
        self._queue.put(job_id)

    def stop(self) -> None:
        """Let the threads finish their current job and exit. A conversion still running
        after the timeout is abandoned (daemon thread); `recover_jobs()` marks that job
        as interrupted on the next start."""
        for _ in self._threads:
            self._queue.put(None)
        for thread in self._threads:
            thread.join(timeout=STOP_TIMEOUT_SECONDS)

    def _work(self) -> None:
        while (job_id := self._queue.get()) is not None:
            try:
                process_job(job_id)
            except Exception:  # never let one job kill the worker thread
                logger.exception("Worker crashed while processing job %s", job_id)


def process_job(job_id: str) -> None:
    """Convert all files of a queued job and store its result. No-op unless the job is
    still `queued` (it may have been processed already)."""
    with SessionLocal() as db:
        claimed = db.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == JobStatus.QUEUED)
            .values(status=JobStatus.PROCESSING, started_at=now())
        ).rowcount
        db.commit()
        if not claimed:
            return

        job = db.get(Job, job_id)
        assert job is not None
        try:
            _convert_files(job)
        except Exception:
            logger.exception("Job %s failed unexpectedly", job_id)
            db.rollback()
            _fail(job, messages.ERROR_MESSAGES[ErrorCode.INTERNAL_ERROR])
        finally:
            storage.remove_uploads(job.id)
            for input_file in job.files:
                input_file.path = None
            db.commit()


def _convert_files(job: Job) -> None:
    target = job.target_format
    names = storage.output_names([f.name for f in job.files], target)
    outputs: list[OutputFile] = []

    for input_file, name in zip(job.files, names, strict=True):
        if input_file.path is None:
            raise RuntimeError(f"input file {input_file.id} has no stored path")
        dst = storage.output_path(job.id, input_file.position, target)
        try:
            convert(
                storage.to_absolute(input_file.path),
                dst,
                input_file.extension,
                target,
                settings.conversion_timeout_seconds,
            )
        except ConversionError as exc:
            template = messages.CONVERSION_TIMEOUT if exc.timeout else messages.CONVERSION_FAILED
            _fail(job, template.format(file=input_file.name))
            return
        outputs.append(
            OutputFile(
                index=input_file.position,
                name=name,
                size=dst.stat().st_size,
                path=storage.to_relative(dst),
            )
        )

    finished_at = now()
    job.status = JobStatus.DONE
    job.result = Result(
        finished_at=finished_at,
        status=ResultStatus.SUCCESS,
        message=messages.CONVERSION_SUCCESS,
        expires_at=finished_at + settings.output_retention_seconds,
        outputs=outputs,
    )


def _fail(job: Job, message: str) -> None:
    storage.remove_outputs(job.id)
    job.status = JobStatus.ERROR
    job.result = Result(
        finished_at=now(), status=ResultStatus.ERROR, message=message, expires_at=None
    )


def recover_jobs() -> list[str]:
    """Called on startup. Jobs that were `processing` when the server stopped become
    errors; `queued` jobs whose uploads still exist are returned (oldest first) to be
    submitted again, the others become errors too."""
    resubmit: list[str] = []
    with SessionLocal() as db:
        unfinished = db.scalars(
            select(Job)
            .where(Job.status.in_([JobStatus.QUEUED, JobStatus.PROCESSING]))
            .order_by(Job.created_at)
        ).all()
        for job in unfinished:
            inputs_present = all(
                f.path is not None and storage.to_absolute(f.path).is_file() for f in job.files
            )
            if job.status is JobStatus.QUEUED and inputs_present:
                resubmit.append(job.id)
                continue
            logger.warning("Job %s was interrupted (status %s)", job.id, job.status)
            _fail(job, messages.JOB_INTERRUPTED)
            storage.remove_uploads(job.id)
            for input_file in job.files:
                input_file.path = None
        db.commit()
    return resubmit
