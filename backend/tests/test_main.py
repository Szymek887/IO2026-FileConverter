from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.auth.deps import CurrentUser
from app.core import db as db_module
from app.core.config import settings
from tests.conftest import FROZEN_AT, TEST_EMAIL


def add_protected_route(app: FastAPI) -> None:
    @app.get("/api/test-protected")
    def protected(user: CurrentUser):
        return {"email": user.email}


def test_startup_creates_data_dir_and_tables(client):
    assert settings.data_dir.is_dir()
    assert "users" in inspect(db_module.engine).get_table_names()


def test_openapi_is_served(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Konwerter plików multimedialnych"


def test_unknown_route_uses_contract_error_shape(client):
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_cors_allows_frontend_origin_with_credentials(client):
    response = client.options(
        "/api/auth/me",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_rejects_other_origins(client):
    response = client.options(
        "/api/auth/me",
        headers={"Origin": "http://evil.test", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in response.headers


def test_protected_route_without_session_is_unauthenticated(app):
    add_protected_route(app)
    with TestClient(app) as client:
        response = client.get("/api/test-protected")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_auth_client_is_authenticated_as_test_user(app, auth_client):
    add_protected_route(app)
    response = auth_client.get("/api/test-protected")
    assert response.status_code == 200
    assert response.json() == {"email": TEST_EMAIL}


def test_clock_fixture(clock):
    assert clock.now() == FROZEN_AT
    clock.advance(601)
    assert clock.now() == FROZEN_AT + 601


def test_each_test_gets_a_fresh_database(db):
    from app.auth.models import User

    assert db.query(User).count() == 0
