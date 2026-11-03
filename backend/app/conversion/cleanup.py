"""Retention: frees the disk of files nobody can download any more.

Every `CLEANUP_INTERVAL_SECONDS` `cleanup_once()` runs in a thread and
- deletes the outputs of jobs past `expires_at` and marks their result `purged`
  (downloads already return `410 FILE_EXPIRED` from that moment on);
- deletes upload directories untouched for `STALE_UPLOAD_SECONDS` that belong to no
  queued/processing job – left by crashed or aborted uploads (inputs of finished jobs are
  deleted by the worker).
"""

import asyncio
import logging
import math
import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from app.conversion import storage
from app.conversion.models import Job, JobStatus, Result
from app.core.clock import now
from app.core.config import settings
from app.core.db import SessionLocal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CleanupReport:
    purged_jobs: int
    removed_uploads: int


def cleanup_once() -> CleanupReport:
    report = CleanupReport(purged_jobs=_purge_expired_outputs(), removed_uploads=_remove_stale())
    if report.purged_jobs or report.removed_uploads:
        logger.info("Cleanup: %s", report)
    return report


def _purge_expired_outputs() -> int:
    purged = 0
    with SessionLocal() as db:
        expired = db.scalars(
            select(Result).where(Result.purged.is_(False), Result.expires_at < now())
        ).all()
        for result in expired:
            shutil.rmtree(storage.output_dir(result.job_id), ignore_errors=True)
            if storage.output_dir(result.job_id).exists():  # e.g. a file still open on Windows
                logger.warning("Could not delete outputs of job %s, retrying later", result.job_id)
                continue
            result.purged = True
            for output in result.outputs:
                output.path = None
            purged += 1
        db.commit()
    return purged


def _remove_stale() -> int:
    root = storage.uploads_root()
    if not root.is_dir():
        return 0
    with SessionLocal() as db:
        active = set(
            db.scalars(
                select(Job.id).where(Job.status.in_([JobStatus.QUEUED, JobStatus.PROCESSING]))
            )
        )
    cutoff = now() - settings.stale_upload_seconds
    removed = 0
    for upload_dir in root.iterdir():
        if upload_dir.name in active or not upload_dir.is_dir():
            continue
        # An upload in progress has no job row yet; its file's mtime grows while it streams.
        if _last_modified(upload_dir) < cutoff:
            shutil.rmtree(upload_dir, ignore_errors=True)
            removed += 1
    return removed


def _last_modified(directory: Path) -> float:
    """Newest mtime of the dir and its files; `inf` (= not stale) if something disappears
    meanwhile – the worker deletes the uploads of a job that just finished."""
    try:
        times = [directory.stat().st_mtime]
        times += [entry.stat().st_mtime for entry in directory.iterdir()]
    except OSError:
        return math.inf
    return max(times)


async def cleanup_loop(interval: float) -> None:
    """Run `cleanup_once()` every `interval` seconds until cancelled (on shutdown)."""
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(cleanup_once)
        except Exception:  # never stop the loop; the next run retries
            logger.exception("Cleanup failed")
