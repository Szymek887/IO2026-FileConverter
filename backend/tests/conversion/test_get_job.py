"""`GET /api/jobs/{job_id}`: polling a job's status and result."""

import pytest

from app.auth.models import User
from app.conversion import converters
from app.conversion.formats import Category, Format
from app.conversion.models import InputFile, Job
from app.conversion.worker import process_job


@pytest.fixture
def create_job(auth_client, media):
    """POST `alpha.png` + `photo.heic` -> jpg and return the 202 body."""

    def create() -> dict:
        response = auth_client.post(
            "/api/jobs",
            files=[
                ("files", ("zdjęcie.png", (media / "alpha.png").read_bytes())),
                ("files", ("IMG_0001.heic", (media / "photo.heic").read_bytes())),
            ],
            data={"target_format": "jpg"},
        )
        assert response.status_code == 202, response.text
        return response.json()

    return create


def assert_error(response, status, code, message):
    assert response.status_code == status, response.text
    assert response.json() == {"status": "error", "code": code, "message": message, "details": None}


def test_queued_job(auth_client, create_job):
    created = create_job()
    response = auth_client.get(f"/api/jobs/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created  # same object as the 202 response
    assert response.json()["status"] == "queued"
    assert response.json()["result"] is None


def test_done_job(auth_client, create_job, clock):
    job_id = create_job()["id"]
    process_job(job_id)  # real image converter

    body = auth_client.get(f"/api/jobs/{job_id}").json()
    assert body["status"] == "done"
    result = body["result"]
    assert result["status"] == "success"
    assert result["message"] == "Konwersja zakończona pomyślnie."
    assert result["finished_at"] == clock.now()
    assert result["expires_at"] == clock.now() + 86400
    assert [(o["index"], o["name"], o["url"]) for o in result["output_files"]] == [
        (0, "zdjęcie.jpg", f"/api/jobs/{job_id}/files/0"),
        (1, "IMG_0001.jpg", f"/api/jobs/{job_id}/files/1"),
    ]
    assert all(o["size"] > 0 for o in result["output_files"])


def test_failed_job(auth_client, create_job, monkeypatch):
    def failing(*args):
        raise converters.ConversionError("broken")

    monkeypatch.setitem(converters.CONVERTERS, Category.IMAGE, failing)
    job_id = create_job()["id"]
    process_job(job_id)

    body = auth_client.get(f"/api/jobs/{job_id}").json()
    assert body["status"] == "error"
    assert body["result"] == {
        "finished_at": body["result"]["finished_at"],
        "status": "error",
        "message": "Nie udało się przekonwertować pliku „zdjęcie.png”.",
        "output_files": [],
        "expires_at": None,
    }


def test_uppercase_id_is_accepted(auth_client, create_job):
    job_id = create_job()["id"]
    assert auth_client.get(f"/api/jobs/{job_id.upper()}").json()["id"] == job_id


@pytest.mark.parametrize(
    "job_id", ["00000000-0000-4000-8000-000000000000", "not-a-uuid", "1' OR '1'='1"]
)
def test_unknown_or_malformed_id_is_not_found(auth_client, job_id):
    assert_error(
        auth_client.get(f"/api/jobs/{job_id}"), 404, "NOT_FOUND", "Nie znaleziono zadania."
    )


def test_other_users_job_is_forbidden(auth_client, db):
    db.add(User(email="someone@example.com"))
    job = Job(user_email="someone@example.com", target_format=Format.JPG)
    job.files = [
        InputFile(position=0, name="a.png", extension=Format.PNG, category=Category.IMAGE, size=1)
    ]
    db.add(job)
    db.commit()

    assert_error(
        auth_client.get(f"/api/jobs/{job.id}"), 403, "FORBIDDEN", "Brak dostępu do tego zadania."
    )


def test_requires_login(client):
    response = client.get("/api/jobs/00000000-0000-4000-8000-000000000000")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
