import asyncio
import email
import logging
from email import policy

import aiosmtplib
import pytest

from app.auth import email as email_module
from app.auth.email import (
    ConsoleEmailSender,
    EmailSendError,
    SmtpEmailSender,
    build_otp_message,
    get_email_sender,
)
from app.core.config import settings

TO = "jan.kowalski@example.com"


@pytest.fixture
def smtp_settings(monkeypatch):
    for name, value in {
        "email_backend": "smtp",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_user": "user",
        "smtp_password": "secret",
        "smtp_from": "Konwerter <noreply@konwerter.example>",
        "smtp_tls": "starttls",
    }.items():
        monkeypatch.setattr(settings, name, value)


@pytest.fixture
def sent(monkeypatch):
    """Captures calls to aiosmtplib.send."""
    calls = []

    async def fake_send(message, **kwargs):
        calls.append((message, kwargs))
        return {}, "OK"

    monkeypatch.setattr(email_module.aiosmtplib, "send", fake_send)
    return calls


def test_otp_message_content(smtp_settings):
    raw = build_otp_message(TO, "004217").as_bytes()
    parsed = email.message_from_bytes(raw, policy=policy.default)

    assert parsed["To"] == TO
    assert parsed["From"] == "Konwerter <noreply@konwerter.example>"
    assert parsed["Subject"] == "Twój kod logowania – Konwerter plików"
    assert parsed["Message-ID"].endswith("@konwerter.example>")
    assert parsed["Date"]
    body = parsed.get_content()
    assert "004217" in body
    assert "ważny przez 10 minut" in body


def test_get_email_sender_follows_setting(monkeypatch, smtp_settings):
    assert isinstance(get_email_sender(), SmtpEmailSender)
    monkeypatch.setattr(settings, "email_backend", "console")
    assert isinstance(get_email_sender(), ConsoleEmailSender)


def test_console_sender_logs_code(caplog):
    with caplog.at_level(logging.INFO, logger="app.auth.email"):
        asyncio.run(ConsoleEmailSender().send_otp(TO, "123456"))
    assert TO in caplog.text
    assert "123456" in caplog.text


def test_smtp_sender_uses_settings(smtp_settings, sent):
    asyncio.run(SmtpEmailSender().send_otp(TO, "123456"))

    ((message, kwargs),) = sent
    assert message["To"] == TO
    assert kwargs == {
        "hostname": "smtp.example.com",
        "port": 587,
        "username": "user",
        "password": "secret",
        "use_tls": False,
        "start_tls": True,
        "timeout": 10,
    }


@pytest.mark.parametrize(
    ("mode", "use_tls", "start_tls"),
    [("starttls", False, True), ("tls", True, False), ("none", False, False)],
)
def test_smtp_tls_modes(monkeypatch, smtp_settings, sent, mode, use_tls, start_tls):
    monkeypatch.setattr(settings, "smtp_tls", mode)
    asyncio.run(SmtpEmailSender().send_otp(TO, "123456"))
    _, kwargs = sent[0]
    assert (kwargs["use_tls"], kwargs["start_tls"]) == (use_tls, start_tls)


def test_smtp_without_credentials_does_not_log_in(monkeypatch, smtp_settings, sent):
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "smtp_password", "")
    asyncio.run(SmtpEmailSender().send_otp(TO, "123456"))
    _, kwargs = sent[0]
    assert kwargs["username"] is None and kwargs["password"] is None


@pytest.mark.parametrize(
    "exc",
    [
        aiosmtplib.SMTPAuthenticationError(535, "bad credentials"),
        aiosmtplib.SMTPConnectError("refused"),
        ConnectionRefusedError(),
        TimeoutError(),
    ],
)
def test_smtp_failure_raises_email_send_error_without_leaking_code(
    monkeypatch, smtp_settings, caplog, exc
):
    async def failing_send(message, **kwargs):
        raise exc

    monkeypatch.setattr(email_module.aiosmtplib, "send", failing_send)
    with pytest.raises(EmailSendError):
        asyncio.run(SmtpEmailSender().send_otp(TO, "123456"))
    assert "123456" not in caplog.text


def test_outbox_fixture_captures_codes(outbox):
    asyncio.run(outbox.send_otp(TO, "111111"))
    asyncio.run(outbox.send_otp(TO, "222222"))
    assert outbox.last_code(TO) == "222222"
