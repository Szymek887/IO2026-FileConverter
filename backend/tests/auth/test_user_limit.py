import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from tests.auth.conftest import login

LIMIT = 10


def email(i: int) -> str:
    return f"user{i}@example.com"


@pytest.fixture
def full(app, outbox, clock):
    """LIMIT users logged in; returns their clients."""
    assert settings.max_active_users == LIMIT
    clients = []
    for i in range(LIMIT):
        client = TestClient(app)
        assert login(client, outbox, email(i)).status_code == 200
        clients.append(client)
    return clients


def test_eleventh_user_is_refused(app, full, outbox):
    response = login(TestClient(app), outbox, "late@example.com")
    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "code": "USER_LIMIT_REACHED",
        "message": (
            "Osiągnięto limit 10 jednocześnie zalogowanych użytkowników. Spróbuj ponownie później."
        ),
        "details": None,
    }
    assert "set-cookie" not in response.headers


def test_refused_user_can_retry_with_the_same_code_after_a_logout(app, full, outbox):
    late = TestClient(app)
    login(late, outbox, "late@example.com")
    code = outbox.last_code("late@example.com")

    full[0].post("/api/auth/logout")

    response = late.post("/api/auth/verify-otp", json={"email": "late@example.com", "code": code})
    assert response.status_code == 200


def test_inactive_users_free_their_slot(app, full, outbox, clock):
    clock.advance(settings.active_window_seconds)
    assert login(TestClient(app), outbox, "late@example.com").status_code == 200


def test_recently_active_users_keep_their_slot(app, full, outbox, clock):
    clock.advance(settings.active_window_seconds - 120)
    for client in full:
        assert client.get("/api/auth/me").status_code == 200  # refreshes last_seen
    clock.advance(120)
    assert login(TestClient(app), outbox, "late@example.com").status_code == 503


def test_active_user_can_log_in_again_when_full(app, full, outbox, clock):
    clock.advance(60)
    assert login(TestClient(app), outbox, email(0)).status_code == 200


def test_expired_sessions_do_not_count(app, full, outbox, clock, monkeypatch):
    monkeypatch.setattr(settings, "active_window_seconds", 10 * 86400)
    clock.advance(settings.session_ttl_seconds)
    assert login(TestClient(app), outbox, "late@example.com").status_code == 200
