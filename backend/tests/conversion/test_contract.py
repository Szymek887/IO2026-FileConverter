"""Contract pass (B17): every error of `POST /api/jobs` and of downloads, compared with the
examples in `docs/openapi.yaml` (code, HTTP status, Polish message, `details`)."""

import pytest
import yaml

from app.auth.models import User
from app.conversion.formats import Category, Format
from app.conversion.models import InputFile, Job
from app.conversion.worker import process_job
from app.core.config import Settings, settings
from app.core.errors import ErrorCode, error
from tests.core.test_errors import OPENAPI_PATH

pytestmark = pytest.mark.skipif(not OPENAPI_PATH.exists(), reason="docs/ not available")

UNKNOWN_JOB = "00000000-0000-4000-8000-000000000000"


@pytest.fixture(scope="module")
def spec() -> dict:
    return yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))


def example(spec, path: str, method: str, status: int) -> dict:
    """The error example documented for `status` of an operation (`$ref`s resolved)."""
    response = spec["paths"][path][method]["responses"][str(status)]
    if "$ref" in response:
        response = spec["components"]["responses"][response["$ref"].rsplit("/", 1)[-1]]
    return response["content"]["application/json"]["example"]


def assert_contract_error(spec, response, status: int, code: str) -> dict:
    """Status and code as expected, body shaped like the `Error` schema."""
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"status", "code", "message", "details"}
    assert (body["status"], body["code"]) == ("error", code)
    documented = spec["components"]["schemas"]["Error"]["properties"]["details"]["properties"]
    assert set(body["details"] or {}) <= set(documented), body["details"]
    return body


def post_job(client, files, target="jpg"):
    return client.post(
        "/api/jobs",
        files=[("files", (name, content)) for name, content in files],
        data={"target_format": target},
    )


# --- POST /api/jobs --------------------------------------------------------------------


def test_too_many_files(spec, auth_client, media):
    jpg = (media / "photo.jpg").read_bytes()
    response = post_job(auth_client, [(f"{i}.jpg", jpg) for i in range(3)])
    body = assert_contract_error(spec, response, 400, "TOO_MANY_FILES")
    assert body == example(spec, "/api/jobs", "post", 400)  # the BadRequest example


def test_file_too_large(spec, auth_client, monkeypatch):
    monkeypatch.setattr(settings, "max_file_size", 100)
    response = post_job(auth_client, [("film.mov", b"x" * 101)], "mp4")
    body = assert_contract_error(spec, response, 413, "FILE_TOO_LARGE")
    documented = example(spec, "/api/jobs", "post", 413)
    assert body["details"] == documented["details"]
    # The example's text with the default limit (a 250 MB upload is too slow for a test):
    default_mb = Settings.model_fields["max_file_size"].default // (1024 * 1024)
    real_limit = error(
        ErrorCode.FILE_TOO_LARGE, file="film.mov", format_args={"limit_mb": default_mb}
    )
    assert real_limit.message == documented["message"]


def test_unsupported_format(spec, auth_client):
    response = post_job(auth_client, [("dokument.pdf", b"%PDF-1.7")])
    body = assert_contract_error(spec, response, 415, "UNSUPPORTED_FORMAT")
    assert body == example(spec, "/api/jobs", "post", 415)


def test_corrupted_file(spec, auth_client, media):
    response = post_job(auth_client, [("zdjecie.png", (media / "notes.txt").read_bytes())])
    body = assert_contract_error(spec, response, 422, "CORRUPTED_FILE")
    assert body == example(spec, "/api/jobs", "post", 422)


def test_invalid_target(spec, auth_client):
    # api-contract.md §2: `Nie można przekonwertować pliku „nagranie.wav” do formatu PNG.`
    response = post_job(auth_client, [("nagranie.wav", b"not probed")], "png")
    body = assert_contract_error(spec, response, 400, "INVALID_TARGET")
    assert body["message"] == "Nie można przekonwertować pliku „nagranie.wav” do formatu PNG."
    assert body["details"] == {"file": "nagranie.wav"}


def test_no_files(spec, auth_client):
    body = assert_contract_error(spec, post_job(auth_client, [("", b"")]), 400, "NO_FILES")
    assert body["details"] is None


def test_validation_error(spec, auth_client):
    response = auth_client.post("/api/jobs", data={"target_format": "jpg"})  # not multipart
    body = assert_contract_error(spec, response, 400, "VALIDATION_ERROR")
    assert set(body["details"]) == {"fields"}


def test_post_requires_login(spec, client):
    response = post_job(client, [("a.jpg", b"x")])
    body = assert_contract_error(spec, response, 401, "UNAUTHENTICATED")
    assert body == example(spec, "/api/jobs", "post", 401)


# --- GET /api/jobs/{job_id}/files/{index} ----------------------------------------------

DOWNLOAD = "/api/jobs/{job_id}/files/{index}"


@pytest.fixture
def done_job(auth_client, media, clock) -> str:
    response = post_job(auth_client, [("zdjęcie.png", (media / "alpha.png").read_bytes())])
    job_id = response.json()["id"]
    process_job(job_id)
    return job_id


def test_download_forbidden(spec, auth_client, db):
    db.add(User(email="someone@example.com"))
    job = Job(user_email="someone@example.com", target_format=Format.JPG)
    job.files = [
        InputFile(position=0, name="a.png", extension=Format.PNG, category=Category.IMAGE, size=1)
    ]
    db.add(job)
    db.commit()
    body = assert_contract_error(
        spec, auth_client.get(f"/api/jobs/{job.id}/files/0"), 403, "FORBIDDEN"
    )
    assert body == example(spec, DOWNLOAD, "get", 403)


def test_download_unknown_job(spec, auth_client):
    response = auth_client.get(f"/api/jobs/{UNKNOWN_JOB}/files/0")
    body = assert_contract_error(spec, response, 404, "NOT_FOUND")
    assert body == example(spec, DOWNLOAD, "get", 404)


def test_download_unknown_index(spec, auth_client, done_job):
    """Same code and status; the message says "file" instead of "job" (contract §2:
    `NOT_FOUND` – job / file does not exist)."""
    body = assert_contract_error(
        spec, auth_client.get(f"/api/jobs/{done_job}/files/5"), 404, "NOT_FOUND"
    )
    assert body == {**example(spec, DOWNLOAD, "get", 404), "message": "Nie znaleziono pliku."}


def test_download_expired(spec, auth_client, done_job, clock):
    clock.advance(settings.output_retention_seconds + 1)
    response = auth_client.get(f"/api/jobs/{done_job}/files/0")
    body = assert_contract_error(spec, response, 410, "FILE_EXPIRED")
    assert body == example(spec, DOWNLOAD, "get", 410)


def test_download_requires_login(spec, client):
    response = client.get(f"/api/jobs/{UNKNOWN_JOB}/files/0")
    body = assert_contract_error(spec, response, 401, "UNAUTHENTICATED")
    assert body == example(spec, DOWNLOAD, "get", 401)


def test_download_headers(spec, auth_client, done_job):
    response = auth_client.get(f"/api/jobs/{done_job}/files/0")
    assert response.status_code == 200
    documented = spec["paths"][DOWNLOAD]["get"]["responses"]["200"]["content"]
    assert response.headers["content-type"] in documented
    # Contract: `attachment; filename*=UTF-8''nagranie.mp3` (+ an ASCII fallback)
    assert response.headers["content-disposition"].startswith("attachment; ")
    assert "filename*=UTF-8''zdj%C4%99cie.jpg" in response.headers["content-disposition"]
