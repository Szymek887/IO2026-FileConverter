import pytest

from app.auth.email import EmailSendError, get_email_sender
from app.auth.models import User
from app.core.config import settings
from app.core.security import verify_otp
from tests.conftest import FROZEN_AT

URL = "/api/auth/request-otp"
EMAIL = "jan.kowalski@example.com"


def request(client, email=EMAIL):
    return client.post(URL, json={"email": email})


def stored_user(db, email=EMAIL) -> User:
    db.expire_all()
    return db.get(User, email)


def test_sends_code_and_returns_contract_body(client, outbox, clock, db):
    response = request(client)

    assert response.status_code == 202
    assert response.json() == {
        "status": "ok",
        "message": f"Wysłaliśmy kod logowania na adres {EMAIL}.",
        "otp_expires": FROZEN_AT + 600,
        "resend_available_in": 60,
    }
    ((to, code),) = outbox.sent
    assert to == EMAIL

    user = stored_user(db)
    assert user.otp_hash != code
    assert verify_otp(EMAIL, code, user.otp_hash)
    assert user.otp_expires == FROZEN_AT + 600
    assert user.otp_sent_at == FROZEN_AT
    assert user.otp_attempts == 0


def test_email_is_normalized(client, outbox, db):
    response = request(client, "  Jan.Kowalski@EXAMPLE.com ")
    assert response.status_code == 202
    assert outbox.sent[0][0] == EMAIL
    assert stored_user(db) is not None


@pytest.mark.parametrize("email", ["", "jan", "jan@", "@example.com", "jan@example", "a b@c.pl"])
def test_invalid_email(client, outbox, email):
    response = request(client, email)
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_EMAIL"
    assert response.json()["message"] == "Podaj poprawny adres e-mail."
    assert outbox.sent == []


@pytest.mark.parametrize("body", [{}, {"email": None}, {"mail": EMAIL}])
def test_malformed_body_is_validation_error(client, outbox, body):
    response = client.post(URL, json=body)
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_domain_allow_list(client, outbox, monkeypatch):
    monkeypatch.setattr(settings, "allowed_email_domains", ["agh.edu.pl"])
    assert request(client, "jan@agh.edu.pl").status_code == 202
    response = request(client, "jan@gmail.com")
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_EMAIL"


def test_resend_too_early_is_rate_limited(client, outbox, clock):
    request(client)
    clock.advance(18)

    response = request(client)
    assert response.status_code == 429
    assert response.json() == {
        "status": "error",
        "code": "OTP_RATE_LIMITED",
        "message": "Nowy kod możesz wysłać za 42 s.",
        "details": {"retry_after_seconds": 42},
    }
    assert len(outbox.sent) == 1


def test_rate_limit_is_per_email(client, outbox, clock):
    request(client)
    assert request(client, "other@example.com").status_code == 202


def test_resend_after_wait_replaces_the_code(client, outbox, clock, db):
    request(client)
    first = outbox.last_code(EMAIL)
    user = stored_user(db)
    user.otp_attempts = 3
    db.commit()

    clock.advance(60)
    assert request(client).status_code == 202

    second = outbox.last_code(EMAIL)
    user = stored_user(db)
    assert verify_otp(EMAIL, second, user.otp_hash)
    assert first == second or not verify_otp(EMAIL, first, user.otp_hash)
    assert user.otp_attempts == 0
    assert user.otp_expires == FROZEN_AT + 60 + 600


def test_existing_user_is_reused(client, outbox, clock, db):
    request(client)
    clock.advance(60)
    request(client)
    assert db.query(User).count() == 1


class FailingSender:
    async def send_otp(self, email, code):
        raise EmailSendError("connection refused")


def test_email_failure_returns_polish_error_and_allows_immediate_retry(
    app, client, outbox, clock, db
):
    app.dependency_overrides[get_email_sender] = lambda: FailingSender()
    response = request(client)
    assert response.status_code == 500
    assert response.json() == {
        "status": "error",
        "code": "INTERNAL_ERROR",
        "message": "Nie udało się wysłać kodu logowania. Spróbuj ponownie później.",
        "details": None,
    }
    assert stored_user(db).otp_hash is None

    app.dependency_overrides[get_email_sender] = lambda: outbox
    assert request(client).status_code == 202


def test_console_backend_works_without_smtp(client, monkeypatch, caplog):
    monkeypatch.setattr(settings, "email_backend", "console")
    assert request(client).status_code == 202
    assert EMAIL in caplog.text
