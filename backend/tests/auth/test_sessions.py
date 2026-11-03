from fastapi.testclient import TestClient

from app.auth.models import User
from app.core.config import settings
from tests.auth.conftest import login
from tests.conftest import FROZEN_AT

EMAIL = "jan.kowalski@example.com"
TTL = 86400


def test_me_without_cookie(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json() == {
        "status": "error",
        "code": "UNAUTHENTICATED",
        "message": "Sesja wygasła. Zaloguj się ponownie.",
        "details": None,
    }


def test_me_with_session(client, outbox, clock):
    login(client, outbox, EMAIL)
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json() == {"email": EMAIL, "session_expires": FROZEN_AT + TTL}


def test_invalid_token(client):
    client.cookies.set("session", "forged-token")
    assert client.get("/api/auth/me").status_code == 401


def test_session_token_is_stored_hashed(client, outbox, clock, db):
    response = login(client, outbox, EMAIL)
    token = response.cookies["session"]
    stored = db.get(User, EMAIL).session_token_hash
    assert stored and stored != token


def test_session_expires_after_ttl_without_activity(client, outbox, clock):
    login(client, outbox, EMAIL)
    clock.advance(TTL - 1)
    assert client.get("/api/auth/me").status_code == 200
    clock.advance(TTL)  # last activity refreshed it; now idle for a full TTL
    assert client.get("/api/auth/me").status_code == 401


def test_activity_slides_expiry_at_most_once_a_minute(client, outbox, clock):
    login(client, outbox, EMAIL)

    clock.advance(30)
    response = client.get("/api/auth/me")
    assert response.json()["session_expires"] == FROZEN_AT + TTL  # too soon to refresh
    assert "set-cookie" not in response.headers

    clock.advance(3600)
    response = client.get("/api/auth/me")
    assert response.json()["session_expires"] == FROZEN_AT + 30 + 3600 + TTL
    assert f"Max-Age={TTL}" in response.headers["set-cookie"]  # cookie lifetime renewed


def test_logout(client, outbox, clock, db):
    login(client, outbox, EMAIL)
    old_token = client.cookies["session"]

    response = client.post("/api/auth/logout")
    assert response.status_code == 204
    assert response.content == b""
    assert 'session=""' in response.headers["set-cookie"]
    assert db.get(User, EMAIL).session_token_hash is None

    client.cookies.set("session", old_token)  # replaying the old cookie doesn't work
    assert client.get("/api/auth/me").status_code == 401


def test_logout_is_idempotent(client):
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.set("session", "forged-token")
    assert client.post("/api/auth/logout").status_code == 204


def test_conversion_endpoints_require_a_real_session(app, outbox, clock):
    anonymous = TestClient(app)
    assert anonymous.get("/api/jobs").status_code == 401
    assert anonymous.get("/api/formats").status_code == 401

    logged_in = TestClient(app)
    login(logged_in, outbox, EMAIL)
    assert logged_in.get("/api/jobs").status_code == 200
    assert logged_in.get("/api/formats").status_code == 200


def test_session_cookie_respects_settings(client, outbox, clock, monkeypatch):
    monkeypatch.setattr(settings, "session_ttl_seconds", 3600)
    response = login(client, outbox, EMAIL)
    assert "Max-Age=3600" in response.headers["set-cookie"]
    assert response.json()["session_expires"] == FROZEN_AT + 3600
