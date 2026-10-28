import re

import pytest

from app.core import security
from app.core.config import settings
from app.core.security import (
    generate_otp,
    hash_otp,
    hash_token,
    new_session_token,
    verify_otp,
)

EMAIL = "jan.kowalski@example.com"


def test_generate_otp_is_six_digits():
    for _ in range(100):
        assert re.fullmatch(r"\d{6}", generate_otp())


@pytest.mark.parametrize(("value", "code"), [(0, "000000"), (42, "000042"), (999_999, "999999")])
def test_generate_otp_is_zero_padded(monkeypatch, value, code):
    monkeypatch.setattr(security.secrets, "randbelow", lambda _: value)
    assert generate_otp() == code


def test_hash_otp_is_deterministic_and_hides_the_code():
    otp_hash = hash_otp(EMAIL, "123456")
    assert otp_hash == hash_otp(EMAIL, "123456")
    assert re.fullmatch(r"[0-9a-f]{64}", otp_hash)
    assert "123456" not in otp_hash


def test_hash_otp_depends_on_email_code_and_secret(monkeypatch):
    original = hash_otp(EMAIL, "123456")
    assert hash_otp("other@example.com", "123456") != original
    assert hash_otp(EMAIL, "123457") != original

    monkeypatch.setattr(settings, "secret_key", "another-secret-key")
    assert hash_otp(EMAIL, "123456") != original


def test_verify_otp():
    otp_hash = hash_otp(EMAIL, "123456")
    assert verify_otp(EMAIL, "123456", otp_hash)
    assert not verify_otp(EMAIL, "654321", otp_hash)
    assert not verify_otp("other@example.com", "123456", otp_hash)


@pytest.mark.parametrize("stored", [None, ""])
def test_verify_otp_without_pending_code(stored):
    assert not verify_otp(EMAIL, "123456", stored)


def test_session_tokens_are_random_and_url_safe():
    tokens = {new_session_token() for _ in range(100)}
    assert len(tokens) == 100
    for token in tokens:
        assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token)  # 32 bytes in base64url


def test_hash_token():
    token = new_session_token()
    assert hash_token(token) == hash_token(token)
    assert re.fullmatch(r"[0-9a-f]{64}", hash_token(token))  # fits User.session_token_hash
    assert hash_token(token) != hash_token(new_session_token())
