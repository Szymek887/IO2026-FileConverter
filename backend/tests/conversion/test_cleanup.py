"""Retention: expired outputs and stale uploads are deleted by `cleanup_once()`."""

import asyncio
import os
import threading
import uuid

import pytest
from fastapi.testclient import TestClient

from app.conversion import cleanup, storage
from app.conversion.cleanup import CleanupReport, cleanup_once
from app.conversion.models import Job
from app.conversion.worker import process_job
from app.core.config import settings

RETENTION = 86400
STALE = 3600


@pytest.fixture
def create_job(auth_client, media, clock):
    """POST `alpha.png` + `photo.heic` -> jpg, return the job ID (still queued)."""

    def create() -> str:
        response = auth_client.post(
            "/api/jobs",
            files=[
                ("files", ("a.png", (media / "alpha.png").read_bytes())),
                ("files", ("b.heic", (media / "photo.heic").read_bytes())),
            ],
            data={"target_format": "jpg"},
        )
        assert response.status_code == 202, response.text
        return response.json()["id"]

    return create


@pytest.fixture
def done_job(create_job) -> str:
    job_id = create_job()
    process_job(job_id)  # real image converter
    return job_id


def load(db, job_id) -> Job:
    db.expire_all()
    return db.get(Job, job_id)


# --- expired outputs -------------------------------------------------------------------


def test_outputs_are_kept_until_expiry(db, done_job, clock):
    clock.advance(RETENTION)  # exactly `expires_at`: still downloadable
    assert cleanup_once() == CleanupReport(purged_jobs=0, removed_uploads=0)
    assert storage.output_dir(done_job).is_dir()
    assert load(db, done_job).result.purged is False


def test_expired_outputs_are_deleted(db, done_job, clock):
    clock.advance(RETENTION + 1)
    assert cleanup_once() == CleanupReport(purged_jobs=1, removed_uploads=0)

    assert not storage.output_dir(done_job).exists()
    result = load(db, done_job).result
    assert result.purged is True
    assert [o.path for o in result.outputs] == [None, None]
    assert [o.name for o in result.outputs] == ["a.jpg", "b.jpg"]  # job history stays

    assert cleanup_once().purged_jobs == 0  # already purged


def test_download_then_cleanup(auth_client, done_job, clock):
    url = f"/api/jobs/{done_job}/files/0"
    clock.advance(RETENTION - 1)
    cleanup_once()
    assert auth_client.get(url).status_code == 200

    clock.advance(2)
    assert auth_client.get(url).status_code == 410  # before the cleanup has run
    cleanup_once()
    assert auth_client.get(url).json()["code"] == "FILE_EXPIRED"
    assert auth_client.get(f"/api/jobs/{done_job}").json()["status"] == "done"


def test_only_expired_jobs_are_purged(db, create_job, clock):
    old = create_job()
    process_job(old)
    clock.advance(RETENTION)
    new = create_job()
    process_job(new)

    clock.advance(1)
    assert cleanup_once().purged_jobs == 1
    assert not storage.output_dir(old).exists()
    assert storage.output_dir(new).is_dir()


def test_failed_jobs_are_ignored(db, create_job, clock, monkeypatch):
    from app.conversion import converters
    from app.conversion.formats import Category

    def failing(*args):
        raise converters.ConversionError("broken")

    monkeypatch.setitem(converters.CONVERTERS, Category.IMAGE, failing)
    job_id = create_job()
    process_job(job_id)
    clock.advance(10 * RETENTION)
    assert cleanup_once().purged_jobs == 0
    assert load(db, job_id).result.purged is False  # nothing to purge, expires_at is NULL


def test_undeletable_outputs_are_retried(db, done_job, clock, monkeypatch):
    clock.advance(RETENTION + 1)
    monkeypatch.setattr(cleanup.shutil, "rmtree", lambda *args, **kwargs: None)
    assert cleanup_once().purged_jobs == 0
    assert load(db, done_job).result.purged is False

    monkeypatch.undo()
    assert cleanup_once().purged_jobs == 1
    assert not storage.output_dir(done_job).exists()


def test_output_dir_already_gone(db, done_job, clock):
    storage.remove_outputs(done_job)
    clock.advance(RETENTION + 1)
    assert cleanup_once().purged_jobs == 1
    assert load(db, done_job).result.purged is True


# --- stale uploads ---------------------------------------------------------------------


def upload_dir(job_id=None, age=0, file_age=None):
    """An upload dir with one file; `age`/`file_age` in seconds before `now()`."""
    from app.core.clock import now

    directory = storage.upload_dir(job_id or str(uuid.uuid4()))
    directory.mkdir(parents=True, exist_ok=True)
    file = directory / "part.png"
    file.write_bytes(b"data")
    file_mtime = now() - (age if file_age is None else file_age)
    os.utime(file, (file_mtime, file_mtime))
    os.utime(directory, (now() - age, now() - age))
    return directory


def test_no_uploads_dir(clock):
    assert not storage.uploads_root().exists()
    assert cleanup_once() == CleanupReport(purged_jobs=0, removed_uploads=0)


def test_stale_orphaned_upload_is_removed(clock):
    stale = upload_dir(age=STALE + 1)
    fresh = upload_dir(age=STALE - 1)
    assert cleanup_once().removed_uploads == 1
    assert not stale.exists()
    assert fresh.is_dir()


def test_upload_still_streaming_is_kept(clock):
    """The dir was created long ago, but the file is still being written."""
    streaming = upload_dir(age=STALE + 100, file_age=5)
    assert cleanup_once().removed_uploads == 0
    assert streaming.is_dir()


def test_uploads_of_queued_jobs_are_kept(db, create_job, clock):
    job_id = create_job()
    upload_dir(job_id, age=10 * STALE)
    assert cleanup_once().removed_uploads == 0
    assert storage.upload_dir(job_id).is_dir()
    assert all(storage.to_absolute(f.path).is_file() for f in load(db, job_id).files)


def test_leftover_uploads_of_finished_jobs_are_removed(done_job, clock):
    leftover = upload_dir(done_job, age=STALE + 1)
    assert cleanup_once().removed_uploads == 1
    assert not leftover.exists()


def test_upload_dir_removed_during_the_scan_is_skipped(clock, monkeypatch):
    """The worker deletes a finished job's uploads while the cleanup looks at them."""
    gone = upload_dir(age=STALE + 1)
    real_iterdir = type(gone).iterdir

    def iterdir(self):
        if self == gone:
            raise FileNotFoundError(self)
        return real_iterdir(self)

    monkeypatch.setattr(type(gone), "iterdir", iterdir)
    assert cleanup_once().removed_uploads == 0


def test_stray_file_in_uploads_root_is_ignored(clock):
    storage.uploads_root().mkdir(parents=True)
    (storage.uploads_root() / "stray.txt").write_bytes(b"x")
    assert cleanup_once().removed_uploads == 0


# --- loop ------------------------------------------------------------------------------


def test_loop_runs_repeatedly_and_survives_errors(monkeypatch):
    calls = 0
    third_call = threading.Event()  # cleanup_once runs in a worker thread

    def fake_cleanup():
        nonlocal calls
        calls += 1
        if calls == 3:
            third_call.set()
        if calls == 1:
            raise RuntimeError("disk on fire")

    monkeypatch.setattr(cleanup, "cleanup_once", fake_cleanup)

    async def run():
        task = asyncio.create_task(cleanup.cleanup_loop(0))
        assert await asyncio.to_thread(third_call.wait, 10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(asyncio.wait_for(run(), timeout=10))
    assert calls >= 3


def test_app_starts_and_stops_the_loop(app, monkeypatch):
    monkeypatch.setattr(settings, "cleanup_interval_seconds", 3600)
    with TestClient(app):
        task = app.state.cleanup_task
        assert task.get_name() == "conversion-cleanup"
        assert not task.done()
    assert not hasattr(app.state, "cleanup_task")
