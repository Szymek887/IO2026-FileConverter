"""Hashing helpers for one-time passwords and session tokens.

Neither codes nor tokens are stored in plain text:
- OTP codes: HMAC-SHA256 keyed with SECRET_KEY. A plain hash of a 6-digit code could be
  brute-forced from a leaked database in milliseconds; without the key it can't.
- Session tokens: SHA-256. Tokens are 256-bit random values, so no key is needed.
"""

import hashlib
import hmac
import secrets

from app.core.config import settings

OTP_LENGTH = 6
SESSION_TOKEN_BYTES = 32


def generate_otp() -> str:
    """Random 6-digit code, zero-padded (e.g. "004217")."""
    return f"{secrets.randbelow(10**OTP_LENGTH):0{OTP_LENGTH}d}"


def hash_otp(email: str, code: str) -> str:
    """HMAC of the code bound to the e-mail, so a code is only valid for its own user.
    `email` must already be normalized (lowercase)."""
    message = f"otp:{email}:{code}".encode()
    return hmac.new(settings.secret_key.encode(), message, hashlib.sha256).hexdigest()


def verify_otp(email: str, code: str, otp_hash: str | None) -> bool:
    """Constant-time check of `code` against the stored hash."""
    if not otp_hash:
        return False
    return hmac.compare_digest(hash_otp(email, code), otp_hash)


def new_session_token() -> str:
    """Random URL-safe token for the session cookie."""
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """SHA-256 hex digest (64 chars) of a session token, as stored in the database."""
    return hashlib.sha256(token.encode()).hexdigest()
