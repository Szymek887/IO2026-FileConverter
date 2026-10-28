import string
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import HTTP_STATUS, AppError, ErrorCode, error, register_exception_handlers
from app.core.messages import ERROR_MESSAGES

OPENAPI_PATH = Path(__file__).parents[3] / "docs" / "openapi.yaml"


class Payload(BaseModel):
    email: str
    code: str


def make_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/app-error")
    def app_error():
        raise error(ErrorCode.FILE_TOO_LARGE, file="film.mov", limit_mb=250)

    @app.post("/validated")
    def validated(payload: Payload):
        return payload

    @app.get("/http-exception/{status}")
    def http_exception(status: int):
        raise HTTPException(status_code=status)

    @app.get("/crash")
    def crash():
        raise RuntimeError("secret internal detail /srv/app")

    return app


@pytest.fixture
def client():
    return TestClient(make_app(), raise_server_exceptions=False)


# --- catalogue consistency ---


def test_every_code_has_message_and_status():
    assert set(ERROR_MESSAGES) == set(ErrorCode)
    assert set(HTTP_STATUS) == set(ErrorCode)


@pytest.mark.skipif(not OPENAPI_PATH.exists(), reason="docs/ not available")
def test_codes_match_api_contract():
    spec = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert set(spec["components"]["schemas"]["ErrorCode"]["enum"]) == set(ErrorCode)


@pytest.mark.parametrize("code", list(ErrorCode))
def test_templates_format_with_their_placeholders(code):
    fields = [f for _, f, _, _ in string.Formatter().parse(ERROR_MESSAGES[code]) if f]
    err = error(code, **dict.fromkeys(fields, "X"))
    assert "{" not in err.message


# --- error() helper ---


def test_error_formats_message_and_sets_details():
    err = error(ErrorCode.OTP_RATE_LIMITED, retry_after_seconds=42)
    assert isinstance(err, AppError)
    assert err.http_status == 429
    assert err.message == "Nowy kod możesz wysłać za 42 s."
    assert err.details == {"retry_after_seconds": 42}


def test_error_without_details_has_none():
    assert error(ErrorCode.NO_FILES).details is None


def test_error_message_override():
    err = error(ErrorCode.NOT_FOUND, message="Nie znaleziono zadania.")
    assert err.message == "Nie znaleziono zadania."
    assert err.http_status == 404


# --- handlers ---


def test_app_error_response(client):
    response = client.get("/app-error")
    assert response.status_code == 413
    assert response.json() == {
        "status": "error",
        "code": "FILE_TOO_LARGE",
        "message": "Plik „film.mov” przekracza maksymalny rozmiar 250 MB.",
        "details": {"file": "film.mov", "limit_mb": 250},
    }


def test_validation_error_response(client):
    response = client.post("/validated", json={"email": "a@b.pl"})
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"] == "Nieprawidłowe dane żądania."
    assert list(body["details"]["fields"]) == ["code"]


def test_malformed_json_is_validation_error(client):
    response = client.post(
        "/validated", content="{not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_unknown_route_is_not_found(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_wrong_method_is_not_found(client):
    response = client.delete("/app-error")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "UNAUTHENTICATED"),
        (403, "FORBIDDEN"),
        (418, "VALIDATION_ERROR"),
        (502, "INTERNAL_ERROR"),
    ],
)
def test_http_exception_mapping(client, status, code):
    response = client.get(f"/http-exception/{status}")
    assert response.status_code == status
    assert response.json()["code"] == code


def test_unexpected_error_hides_internals(client, caplog):
    response = client.get("/crash")
    assert response.status_code == 500
    assert response.json() == {
        "status": "error",
        "code": "INTERNAL_ERROR",
        "message": "Wystąpił nieoczekiwany błąd serwera.",
        "details": None,
    }
    assert "secret internal detail" in caplog.text  # logged, not returned
