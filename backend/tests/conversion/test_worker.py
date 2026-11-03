"""Job lifecycle: queued -> processing -> done/error, worker threads, restart recovery.

Jobs are created through `POST /api/jobs` with sample images; the image converter is
replaced by a fake so these tests don't depend on the real converters.
"""

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.conversion import converters, storage
from app.conversion.formats import Category
from app.conversion.models import Job, JobStatus, ResultStatus
from app.conversion.worker import ThreadedJobRunner, process_job, recover_jobs
from app.core.config import settings
from app.core.errors import ERROR_MESSAGES, ErrorCode
from app.main import create_app


class FakeConverter:
    """Writes `b"converted:<n>"`; fails (or times out) on the given call number."""

    def __init__(self) -> None:
        self.calls = 0
        self.fail_on: int | None = None
        self.timeout = False

    def __call__(self, src, dst, source, target, timeout):
        self.calls += 1
        assert timeout == settings.conversion_timeout_seconds
        if self.calls == self.fail_on:
            dst.write_bytes(b"partial")
            raise converters.ConversionError("boom", timeout=self.timeout)
        dst.write_bytes(f"converted:{self.calls}".encode())


@pytest.fixture
def fake(monkeypatch) -> FakeConverter:
    converter = FakeConverter()
    monkeypatch.setattr(converters, "CONVERTERS", {Category.IMAGE: converter})
    return converter


@pytest.fixture
def make_job(auth_client, media):
    """POST a job with two images (`zdjęcie.png`, `foto.jpg`) to `heic`; return its ID."""

    def make(files=("alpha.png", "photo.jpg"), names=("zdjęcie.png", "foto.jpg")) -> str:
        response = auth_client.post(
            "/api/jobs",
            files=[
                ("files", (name, (media / f).read_bytes()))
                for f, name in zip(files, names, strict=True)
            ],
            data={"target_format": "heic"},
        )
        assert response.status_code == 202, response.text
        return response.json()["id"]

    return make


def load(db, job_id) -> Job:
    db.expire_all()
    return db.get(Job, job_id)


def test_successful_job(db, fake, make_job, clock):
    job_id = make_job()
    process_job(job_id)

    job = load(db, job_id)
    assert job.status is JobStatus.DONE
    assert job.started_at == clock.now()
    result = job.result
    assert result.status is ResultStatus.SUCCESS
    assert result.message == "Konwersja zakończona pomyślnie."
    assert result.finished_at == clock.now()
    assert result.expires_at == clock.now() + settings.output_retention_seconds
    assert [(o.index, o.name) for o in result.outputs] == [(0, "zdjęcie.heic"), (1, "foto.heic")]
    for out in result.outputs:
        path = storage.to_absolute(out.path)
        assert path == storage.output_path(job_id, out.index, job.target_format)
        assert out.size == path.stat().st_size
        assert not path.with_name(path.name + ".part").exists()
    # Inputs are gone once the job is finished.
    assert not storage.upload_dir(job_id).exists()
    assert all(f.path is None for f in job.files)


def test_duplicate_names_get_unique_output_names(db, fake, make_job):
    job_id = make_job(names=("foto.png", "foto.jpg"))
    process_job(job_id)
    assert [o.name for o in load(db, job_id).result.outputs] == ["foto.heic", "foto (2).heic"]


def test_finished_job_serializes_download_urls(db, fake, make_job):
    from app.conversion.jobs import job_response  # GET /api/jobs/{id} arrives in B11

    job_id = make_job()
    process_job(job_id)
    body = job_response(load(db, job_id)).model_dump(mode="json")
    assert body["status"] == "done"
    assert body["result"]["output_files"][1]["url"] == f"/api/jobs/{job_id}/files/1"


@pytest.mark.parametrize(
    ("timeout", "message"),
    [
        (False, "Nie udało się przekonwertować pliku „foto.jpg”."),
        (True, "Konwersja pliku „foto.jpg” trwała zbyt długo i została przerwana."),
    ],
)
def test_failing_file_fails_whole_job(db, fake, make_job, timeout, message):
    fake.fail_on, fake.timeout = 2, timeout
    job_id = make_job()
    process_job(job_id)

    job = load(db, job_id)
    assert job.status is JobStatus.ERROR
    assert job.result.status is ResultStatus.ERROR
    assert job.result.message == message
    assert job.result.outputs == []
    assert job.result.expires_at is None
    # The first file's output and the partial second one are removed, inputs too.
    assert not storage.output_dir(job_id).exists()
    assert not storage.upload_dir(job_id).exists()


def test_first_failure_stops_the_job(db, fake, make_job):
    fake.fail_on = 1
    job_id = make_job()
    process_job(job_id)
    assert fake.calls == 1
    assert "zdjęcie.png" in load(db, job_id).result.message


def test_unexpected_error_is_reported_generically(db, fake, make_job, monkeypatch):
    def broken(*args):
        raise RuntimeError("bug")

    monkeypatch.setattr(storage, "output_names", broken)
    job_id = make_job()
    process_job(job_id)

    job = load(db, job_id)
    assert job.status is JobStatus.ERROR
    assert job.result.message == ERROR_MESSAGES[ErrorCode.INTERNAL_ERROR]
    assert not storage.upload_dir(job_id).exists()


def test_job_is_processed_only_once(db, fake, make_job):
    job_id = make_job()
    process_job(job_id)
    process_job(job_id)  # e.g. submitted twice
    assert fake.calls == 2  # two files, converted once each
    assert load(db, job_id).status is JobStatus.DONE


def test_unknown_job_is_ignored(fake):
    process_job("00000000-0000-4000-8000-000000000000")
    assert fake.calls == 0


# --- worker threads --------------------------------------------------------------------


def wait_for(db, job_id, status, timeout=10.0) -> Job:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = load(db, job_id)
        if job.status is status:
            return job
        time.sleep(0.02)
    pytest.fail(f"job {job_id} did not reach {status} (is {job.status})")


def test_threaded_runner_processes_jobs(db, fake, make_job):
    job_ids = [make_job(), make_job()]
    runner = ThreadedJobRunner(worker_count=2)
    runner.start()
    try:
        for job_id in job_ids:
            runner.submit(job_id)
        for job_id in job_ids:
            assert wait_for(db, job_id, JobStatus.DONE).result.status is ResultStatus.SUCCESS
    finally:
        runner.stop()
    assert not any(t.is_alive() for t in runner._threads)


def test_worker_thread_survives_crash(db, fake, make_job, monkeypatch):
    from app.conversion import worker

    real_process_job = worker.process_job
    calls = []

    def flaky(job_id):
        calls.append(job_id)
        if len(calls) == 1:
            raise RuntimeError("crash outside the job's own error handling")
        real_process_job(job_id)

    monkeypatch.setattr(worker, "process_job", flaky)
    runner = ThreadedJobRunner(worker_count=1)
    runner.start()
    try:
        runner.submit("crashing-job")
        job_id = make_job()
        runner.submit(job_id)
        wait_for(db, job_id, JobStatus.DONE)
    finally:
        runner.stop()


def test_app_starts_and_stops_worker_threads(monkeypatch):
    monkeypatch.setattr(settings, "worker_count", 3)
    app = create_app()
    with TestClient(app):
        runner = app.state.job_runner
        assert isinstance(runner, ThreadedJobRunner)
        assert sum(t.is_alive() for t in runner._threads) == 3
    assert not hasattr(app.state, "job_runner")
    assert not any(t.is_alive() for t in runner._threads)


# --- restart recovery ------------------------------------------------------------------


def test_recovery(db, make_job):
    requeue = make_job()
    interrupted = make_job()
    missing_inputs = make_job()
    done = make_job()

    for job_id, status in ((interrupted, JobStatus.PROCESSING), (done, JobStatus.DONE)):
        load(db, job_id).status = status
        db.commit()  # before the next load(): expire_all() would drop the change
    storage.remove_uploads(missing_inputs)

    assert recover_jobs() == [requeue]

    assert load(db, requeue).status is JobStatus.QUEUED
    assert load(db, done).status is JobStatus.DONE
    for job_id in (interrupted, missing_inputs):
        job = load(db, job_id)
        assert job.status is JobStatus.ERROR
        assert job.result.message == "Przetwarzanie zostało przerwane. Spróbuj ponownie."
        assert not storage.upload_dir(job_id).exists()
        assert all(f.path is None for f in job.files)


def test_startup_resubmits_queued_jobs(app, db, make_job):
    job_id = make_job()
    app.state.job_runner.submitted.clear()

    with TestClient(app):  # second startup of the same app = server restart
        assert app.state.job_runner.submitted == [job_id]
    assert db.scalars(select(Job.status)).all() == [JobStatus.QUEUED]
