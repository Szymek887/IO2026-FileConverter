import pytest
from fastapi.testclient import TestClient

from app.auth.models import User
from app.core.config import settings
from tests.auth.conftest import login
from tests.conftest import FROZEN_AT

EMAIL = "jan.kowalski@example.com"
VERIFY = "/api/auth/verify-otp"


@pytest.fixture
def code(client, outbox, clock):
    client.post("/api/auth/request-otp", json={"email": EMAIL})
    return outbox.last_code(EMAIL)


def verify(client, code, email=EMAIL):
    return client.post(VERIFY, json={"email": email, "code": code})


def wrong(code: str) -> str:
    return f"{(int(code) + 1) % 1_000_000:06d}"


def test_correct_code_logs_in(client, code):
    response = verify(client, code)

    assert response.status_code == 200
    assert response.json() == {"email": EMAIL, "session_expires": FROZEN_AT + 86400}
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("session=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/" in cookie
    assert "Max-Age=86400" in cookie
    assert "Secure" not in cookie  # COOKIE_SECURE=false in these tests


def test_cookie_is_secure_when_configured(client, code, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", True)
    assert "Secure" in verify(client, code).headers["set-cookie"]


def test_email_is_case_insensitive(client, code):
    assert verify(client, code, email=" Jan.Kowalski@EXAMPLE.com").status_code == 200


def test_wrong_code(client, code, db):
    response = verify(client, wrong(code))
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_OTP"
    assert response.json()["message"] == "Nieprawidłowy kod logowania."
    assert "set-cookie" not in response.headers
    assert db.get(User, EMAIL).otp_attempts == 1


def test_fifth_wrong_code_locks_and_correct_code_is_then_rejected(client, code, outbox, clock):
    for _ in range(settings.otp_max_attempts - 1):
        assert verify(client, wrong(code)).json()["code"] == "INVALID_OTP"

    response = verify(client, wrong(code))
    assert response.status_code == 429
    assert response.json()["code"] == "TOO_MANY_ATTEMPTS"

    assert verify(client, code).json()["code"] == "OTP_EXPIRED"
    # The resend limit still applies after a lockout (no unlimited guessing).
    resend = client.post("/api/auth/request-otp", json={"email": EMAIL})
    assert resend.status_code == 429


def test_expired_code(client, code, clock):
    clock.advance(settings.otp_ttl_seconds)
    response = verify(client, code)
    assert response.status_code == 401
    assert response.json()["code"] == "OTP_EXPIRED"
    assert response.json()["message"] == "Kod logowania wygasł. Poproś o nowy kod."


def test_code_valid_until_just_before_expiry(client, code, clock):
    clock.advance(settings.otp_ttl_seconds - 1)
    assert verify(client, code).status_code == 200


def test_code_can_be_used_only_once(client, code):
    assert verify(client, code).status_code == 200
    assert verify(client, code).json()["code"] == "OTP_EXPIRED"


def test_unknown_email(client, clock):
    assert verify(client, "123456", email="nobody@example.com").json()["code"] == "OTP_EXPIRED"


def test_code_of_another_user_is_rejected(client, outbox, clock):
    client.post("/api/auth/request-otp", json={"email": "a@example.com"})
    client.post("/api/auth/request-otp", json={"email": "b@example.com"})
    code_a, code_b = outbox.last_code("a@example.com"), outbox.last_code("b@example.com")
    if code_a == code_b:
        pytest.skip("both random codes happen to be equal")
    assert verify(client, code_a, email="b@example.com").json()["code"] == "INVALID_OTP"


@pytest.mark.parametrize("bad", ["12345", "1234567", "abcdef", "12 456", ""])
def test_code_must_be_six_digits(client, code, bad):
    response = verify(client, bad)
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert "code" in response.json()["details"]["fields"]


def test_new_login_replaces_previous_session(app, client, outbox, clock):
    first = TestClient(app)
    second = TestClient(app)
    assert login(first, outbox, EMAIL).status_code == 200
    clock.advance(60)
    assert login(second, outbox, EMAIL).status_code == 200

    assert second.get("/api/auth/me").status_code == 200
    assert first.get("/api/auth/me").status_code == 401
