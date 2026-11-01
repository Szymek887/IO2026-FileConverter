"""`POST /api/jobs`: upload, validation (all contract error codes) and the queued job."""

import uuid

import pytest
from sqlalchemy import select

from app.conversion import storage
from app.conversion.models import InputFile, Job, JobStatus
from app.core.config import settings
from tests.conftest import TEST_EMAIL
from tests.conversion.conftest import requires_ffmpeg


def post_job(client, files, target="jpg"):
    """`files`: list of (filename, content bytes). `target=None` omits the field."""
    data = {} if target is None else {"target_format": target}
    return client.post(
        "/api/jobs", files=[("files", (name, content)) for name, content in files], data=data
    )


def sample(media, name, upload_name=None):
    return (upload_name or name, (media / name).read_bytes())


def assert_error(response, status, code, message=None, file=None):
    assert response.status_code == status, response.text
    body = response.json()
    assert body["status"] == "error"
    assert body["code"] == code
    if message is not None:
        assert body["message"] == message
    if file is not None:
        assert body["details"]["file"] == file


def assert_nothing_stored(db):
    assert db.scalars(select(Job)).all() == []
    root = storage.uploads_root()
    assert not root.exists() or list(root.iterdir()) == []


# --- success ---------------------------------------------------------------------------


def test_creates_queued_job(auth_client, app, db, media, clock):
    response = post_job(auth_client, [sample(media, "alpha.png", "zdjęcie.png")], "jpg")

    assert response.status_code == 202, response.text
    body = response.json()
    assert uuid.UUID(body["id"]).version == 4
    assert body == {
        "id": body["id"],
        "created_at": clock.now(),
        "target_format": "jpg",
        "status": "queued",
        "files": [
            {
                "id": body["files"][0]["id"],
                "name": "zdjęcie.png",
                "extension": "png",
                "category": "image",
                "size": (media / "alpha.png").stat().st_size,
            }
        ],
        "result": None,
    }
    assert app.state.job_runner.submitted == [body["id"]]

    job = db.get(Job, body["id"])
    assert job.user_email == TEST_EMAIL
    assert job.status is JobStatus.QUEUED
    stored = job.files[0]
    assert stored.path == f"uploads/{job.id}/{stored.id}.png"
    assert storage.to_absolute(stored.path).read_bytes() == (media / "alpha.png").read_bytes()


def test_two_images_keep_upload_order(auth_client, db, media):
    response = post_job(
        auth_client, [sample(media, "photo.heic"), sample(media, "photo.jpg", "b.JPEG")], "png"
    )
    assert response.status_code == 202, response.text
    files = response.json()["files"]
    assert [(f["name"], f["extension"]) for f in files] == [
        ("photo.heic", "heic"),
        ("b.JPEG", "jpg"),
    ]
    positions = db.scalars(select(InputFile.position).order_by(InputFile.position)).all()
    assert positions == [0, 1]


def test_target_is_case_insensitive(auth_client, media):
    response = post_job(auth_client, [sample(media, "photo.jpg")], "PNG")
    assert response.status_code == 202
    assert response.json()["target_format"] == "png"


@requires_ffmpeg
def test_audio_batch(auth_client, media):
    response = post_job(
        auth_client, [sample(media, "stereo16.wav"), sample(media, "mono24.flac")], "mp3"
    )
    assert response.status_code == 202, response.text
    assert [f["category"] for f in response.json()["files"]] == ["audio", "audio"]


@requires_ffmpeg
def test_mp4_to_mov(auth_client, media):
    assert post_job(auth_client, [sample(media, "clip.mp4")], "mov").status_code == 202


# --- validation errors -----------------------------------------------------------------


def test_no_files(auth_client, db):
    # What a browser FormData sends for an <input type="file"> with nothing selected.
    response = post_job(auth_client, [("", b"")], "jpg")
    assert_error(response, 400, "NO_FILES", "Nie wybrano żadnego pliku.")
    assert_nothing_stored(db)


def test_non_multipart_body(auth_client, db):
    response = auth_client.post("/api/jobs", data={"target_format": "jpg"})  # urlencoded
    assert_error(response, 400, "VALIDATION_ERROR")
    assert_nothing_stored(db)


def test_missing_target(auth_client, db, media):
    response = post_job(auth_client, [sample(media, "photo.jpg")], target=None)
    assert_error(response, 400, "VALIDATION_ERROR")
    assert "target_format" in response.json()["details"]["fields"]
    assert_nothing_stored(db)


@pytest.mark.parametrize(
    ("target", "shown"),
    [("jpg", "JPG"), ("mp3", "MP3"), ("exe", "EXE"), ("jpeg", "JPG")],
)
def test_invalid_target(auth_client, db, media, target, shown):
    response = post_job(auth_client, [sample(media, "photo.jpg")], target)
    assert_error(
        response,
        400,
        "INVALID_TARGET",
        f"Nie można przekonwertować pliku „photo.jpg” do formatu {shown}.",
        file="photo.jpg",
    )
    assert_nothing_stored(db)


def test_invalid_target_names_the_file_from_other_category(auth_client, db, media):
    # Rule 7 runs before any content check, so the .wav content doesn't matter here.
    response = post_job(
        auth_client,
        [("nagranie.wav", b"not probed"), sample(media, "photo.jpg", "foto.jpg")],
        "mp3",
    )
    assert_error(response, 400, "INVALID_TARGET", file="foto.jpg")
    assert_nothing_stored(db)


def test_renamed_text_file_is_corrupted(auth_client, db, media):
    response = post_job(auth_client, [sample(media, "notes.txt", "zdjecie.png")], "jpg")
    assert_error(
        response,
        422,
        "CORRUPTED_FILE",
        "Plik „zdjecie.png” jest uszkodzony lub nie jest prawidłowym obrazem.",
        file="zdjecie.png",
    )
    assert_nothing_stored(db)


def test_second_file_corrupted_rejects_whole_job(auth_client, app, db, media):
    response = post_job(
        auth_client, [sample(media, "photo.jpg"), sample(media, "truncated.jpg", "b.jpg")], "png"
    )
    assert_error(response, 422, "CORRUPTED_FILE", file="b.jpg")
    assert_nothing_stored(db)
    assert app.state.job_runner.submitted == []


@requires_ffmpeg
@pytest.mark.parametrize(
    ("name", "upload_name", "target", "kind"),
    [
        ("notes.txt", "film.mp4", "gif", "plikiem wideo"),
        ("audio_only.mp4", "film.mp4", "mov", "plikiem wideo"),
        ("stereo16.wav", "song.flac", "mp3", "plikiem audio"),
    ],
)
def test_corrupted_audio_video(auth_client, db, media, name, upload_name, target, kind):
    response = post_job(auth_client, [sample(media, name, upload_name)], target)
    assert_error(
        response,
        422,
        "CORRUPTED_FILE",
        f"Plik „{upload_name}” jest uszkodzony lub nie jest prawidłowym {kind}.",
    )
    assert_nothing_stored(db)


def test_unsupported_format(auth_client, db):
    response = post_job(auth_client, [("dokument.pdf", b"%PDF-1.7")], "jpg")
    assert_error(
        response, 415, "UNSUPPORTED_FORMAT", "Format pliku „dokument.pdf” nie jest obsługiwany."
    )
    assert_nothing_stored(db)


def test_too_many_files(auth_client, db, media):
    response = post_job(auth_client, [sample(media, "photo.jpg", f"{i}.jpg") for i in range(3)])
    assert_error(response, 400, "TOO_MANY_FILES", "Możesz przesłać maksymalnie 2 pliki naraz.")
    assert_nothing_stored(db)


def test_file_too_large(auth_client, db, media, monkeypatch):
    monkeypatch.setattr(settings, "max_file_size", 100)
    response = post_job(auth_client, [sample(media, "photo.jpg", "film.jpg")], "png")
    assert_error(response, 413, "FILE_TOO_LARGE", file="film.jpg")
    assert_nothing_stored(db)


def test_requires_login(client, db, media):
    response = post_job(client, [sample(media, "photo.jpg")], "png")
    assert_error(response, 401, "UNAUTHENTICATED")
    assert not storage.uploads_root().exists()  # body never read


def test_openapi_documents_multipart_body(client):
    operation = client.get("/openapi.json").json()["paths"]["/api/jobs"]["post"]
    schema = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert schema["required"] == ["files", "target_format"]
    assert "202" in operation["responses"]
