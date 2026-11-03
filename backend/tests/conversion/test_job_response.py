"""Serialization of finished jobs into the contract's Job object (used by GET endpoints)."""

from app.conversion.formats import Category, Format
from app.conversion.jobs import job_response
from app.conversion.models import InputFile, Job, JobStatus, OutputFile, Result, ResultStatus

JOB_ID = "7f3a9c2e-4b1d-4e8a-9c3f-2a1b5d6e7f80"


def make_job(status, result=None) -> Job:
    return Job(
        id=JOB_ID,
        created_at=1793102400,
        target_format=Format.MP3,
        status=status,
        files=[
            InputFile(
                id="f1",
                position=0,
                name="nagranie.wav",
                extension=Format.WAV,
                category=Category.AUDIO,
                size=52428800,
            )
        ],
        result=result,
    )


def test_done_job_matches_contract_example():
    job = make_job(
        JobStatus.DONE,
        Result(
            finished_at=1793102461,
            status=ResultStatus.SUCCESS,
            message="Konwersja zakończona pomyślnie.",
            expires_at=1793188861,
            outputs=[OutputFile(index=0, name="nagranie.mp3", size=4812345)],
        ),
    )
    assert job_response(job).model_dump(mode="json")["result"] == {
        "finished_at": 1793102461,
        "status": "success",
        "message": "Konwersja zakończona pomyślnie.",
        "output_files": [
            {
                "index": 0,
                "name": "nagranie.mp3",
                "size": 4812345,
                "url": f"/api/jobs/{JOB_ID}/files/0",
            }
        ],
        "expires_at": 1793188861,
    }


def test_error_job_has_no_outputs():
    job = make_job(
        JobStatus.ERROR,
        Result(
            finished_at=1793102480,
            status=ResultStatus.ERROR,
            message="Nie udało się przekonwertować pliku „nagranie.wav”.",
            expires_at=None,
        ),
    )
    body = job_response(job).model_dump(mode="json")
    assert body["status"] == "error"
    assert body["result"]["status"] == "error"
    assert body["result"]["output_files"] == []
    assert body["result"]["expires_at"] is None
