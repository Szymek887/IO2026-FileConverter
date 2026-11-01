"""`GET /api/jobs/{job_id}/files/{index}`: downloading converted files."""

import pytest

from app.auth.models import User
from app.conversion import converters, storage
from app.conversion.formats import Category, Format
from app.conversion.models import InputFile, Job
from app.conversion.worker import process_job
from tests.conversion.conftest import requires_ffmpeg

NOT_FOUND = (404, "NOT_FOUND", "Nie znaleziono pliku.")
EXPIRED = (410, "FILE_EXPIRED", "Plik wynikowy wygasł. Wykonaj konwersję ponownie.")


@pytest.fixture
def create_job(auth_client, media):
    """POST `alpha.png` + `photo.heic` -> jpg, return the job ID (still queued)."""

    def create() -> str:
        response = auth_client.post(
            "/api/jobs",
            files=[
                ("files", ("zdjęcie.png", (media / "alpha.png").read_bytes())),
                ("files", ("IMG_0001.heic", (media / "photo.heic").read_bytes())),
            ],
            data={"target_format": "jpg"},
        )
        assert response.status_code == 202, response.text
        return response.json()["id"]

    return create


@pytest.fixture
def done_job(create_job, clock) -> str:
    job_id = create_job()
    process_job(job_id)  # real image converter
    return job_id


def assert_error(response, status, code, message):
    assert response.status_code == status, response.text
    assert response.json() == {"status": "error", "code": code, "message": message, "details": None}


def stored_output(db, job_id, index=0):
    return db.get(Job, job_id).result.outputs[index]


def test_download(auth_client, db, done_job):
    response = auth_client.get(f"/api/jobs/{done_job}/files/1")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    output = stored_output(db, done_job, 1)
    assert response.content == storage.to_absolute(output.path).read_bytes()
    assert len(response.content) == output.size
    assert response.headers["content-disposition"] == (
        "attachment; filename=\"IMG_0001.jpg\"; filename*=UTF-8''IMG_0001.jpg"
    )


def test_polish_name_header(auth_client, done_job):
    response = auth_client.get(f"/api/jobs/{done_job}/files/0")
    assert response.headers["content-disposition"] == (
        "attachment; filename=\"zdjecie.jpg\"; filename*=UTF-8''zdj%C4%99cie.jpg"
    )


def test_url_from_job_response_works(auth_client, done_job):
    outputs = auth_client.get(f"/api/jobs/{done_job}").json()["result"]["output_files"]
    assert [auth_client.get(o["url"]).status_code for o in outputs] == [200, 200]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("plik.mp3", "attachment; filename=\"plik.mp3\"; filename*=UTF-8''plik.mp3"),
        (
            'a"b\\c.mp3',
            "attachment; filename=\"abc.mp3\"; filename*=UTF-8''a%22b%5Cc.mp3",
        ),
        (
            "za;żó ł 100%.mp3",
            'attachment; filename="za;zo  100%.mp3"; '
            "filename*=UTF-8''za%3B%C5%BC%C3%B3%20%C5%82%20100%25.mp3",
        ),
        (
            "日本語.mp3",
            "attachment; filename=\"plik.mp3\"; filename*=UTF-8''%E6%97%A5%E6%9C%AC%E8%AA%9E.mp3",
        ),
    ],
)
def test_content_disposition(name, expected):
    assert storage.content_disposition(name) == expected


@requires_ffmpeg
def test_audio_content_type(auth_client, media):
    response = auth_client.post(
        "/api/jobs",
        files=[("files", ("nagranie.wav", (media / "stereo16.wav").read_bytes()))],
        data={"target_format": "mp3"},
    )
    job_id = response.json()["id"]
    process_job(job_id)

    response = auth_client.get(f"/api/jobs/{job_id}/files/0")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"


def test_queued_job_has_no_files(auth_client, create_job):
    assert_error(auth_client.get(f"/api/jobs/{create_job()}/files/0"), *NOT_FOUND)


def test_failed_job_has_no_files(auth_client, create_job, monkeypatch):
    def failing(*args):
        raise converters.ConversionError("broken")

    monkeypatch.setitem(converters.CONVERTERS, Category.IMAGE, failing)
    job_id = create_job()
    process_job(job_id)
    assert_error(auth_client.get(f"/api/jobs/{job_id}/files/0"), *NOT_FOUND)


@pytest.mark.parametrize("index", ["2", "5", "-1", "abc", "01", "%2B1", "1_0", "1.0", "9" * 5000])
def test_bad_index_is_not_found(auth_client, done_job, index):
    assert_error(auth_client.get(f"/api/jobs/{done_job}/files/{index}"), *NOT_FOUND)


@pytest.mark.parametrize("job_id", ["00000000-0000-4000-8000-000000000000", "not-a-uuid"])
def test_unknown_job(auth_client, job_id):
    response = auth_client.get(f"/api/jobs/{job_id}/files/0")
    assert_error(response, 404, "NOT_FOUND", "Nie znaleziono zadania.")


def test_other_users_job_is_forbidden(auth_client, db):
    db.add(User(email="someone@example.com"))
    job = Job(user_email="someone@example.com", target_format=Format.JPG)
    job.files = [
        InputFile(position=0, name="a.png", extension=Format.PNG, category=Category.IMAGE, size=1)
    ]
    db.add(job)
    db.commit()

    response = auth_client.get(f"/api/jobs/{job.id}/files/0")
    assert_error(response, 403, "FORBIDDEN", "Brak dostępu do tego zadania.")


def test_available_until_expires_at_then_gone(auth_client, done_job, clock):
    url = f"/api/jobs/{done_job}/files/0"
    clock.advance(86400)  # exactly `expires_at`
    assert auth_client.get(url).status_code == 200
    clock.advance(1)
    assert_error(auth_client.get(url), *EXPIRED)


def test_purged_job_is_expired(auth_client, db, done_job):
    db.get(Job, done_job).result.purged = True
    db.commit()
    assert_error(auth_client.get(f"/api/jobs/{done_job}/files/0"), *EXPIRED)


def test_file_missing_on_disk_is_expired(auth_client, db, done_job):
    storage.to_absolute(stored_output(db, done_job).path).unlink()
    assert_error(auth_client.get(f"/api/jobs/{done_job}/files/0"), *EXPIRED)


def test_output_without_path_is_expired(auth_client, db, done_job):
    stored_output(db, done_job).path = None
    db.commit()
    assert_error(auth_client.get(f"/api/jobs/{done_job}/files/0"), *EXPIRED)


def test_bad_index_of_expired_job_is_still_not_found(auth_client, done_job, clock):
    clock.advance(86401)
    assert_error(auth_client.get(f"/api/jobs/{done_job}/files/2"), *NOT_FOUND)


def test_requires_login(client):
    response = client.get("/api/jobs/00000000-0000-4000-8000-000000000000/files/0")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
