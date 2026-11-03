"""Sessions: one per user, identified by a random token in the `session` cookie.

Only the token's SHA-256 is stored. A session expires SESSION_TTL_SECONDS after the last
activity (sliding expiry, refreshed at most once per REFRESH_INTERVAL_SECONDS so status
polling doesn't write to the database on every request).
"""

from fastapi import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.config import settings
from app.core.security import hash_token, new_session_token

SESSION_COOKIE = "session"
REFRESH_INTERVAL_SECONDS = 60


def create_session(user: User, at: int) -> str:
    """Start a new session (replacing any previous one) and return its token."""
    token = new_session_token()
    user.session_token_hash = hash_token(token)
    user.session_expires = at + settings.session_ttl_seconds
    user.last_seen = at
    return token


def end_session(user: User) -> None:
    user.session_token_hash = None
    user.session_expires = None
    user.last_seen = None


def find_session_user(db: Session, token: str, at: int) -> User | None:
    """User owning a valid (not expired) session with this token."""
    user = db.scalar(select(User).where(User.session_token_hash == hash_token(token)))
    if user is None or (user.session_expires or 0) <= at:
        return None
    return user


def refresh_session(user: User, at: int) -> bool:
    """Extend the session if the last refresh is older than REFRESH_INTERVAL_SECONDS.
    Returns whether anything changed (caller commits and re-sends the cookie)."""
    if at - (user.last_seen or 0) < REFRESH_INTERVAL_SECONDS:
        return False
    user.last_seen = at
    user.session_expires = at + settings.session_ttl_seconds
    return True


# --- Concurrent user limit ---


def _active_since(at: int) -> int:
    return at - settings.active_window_seconds


def is_active(user: User, at: int) -> bool:
    """Valid session and a request within ACTIVE_WINDOW_SECONDS."""
    return (
        user.session_token_hash is not None
        and (user.session_expires or 0) > at
        and (user.last_seen or 0) > _active_since(at)
    )


def count_active_users(db: Session, at: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(User)
        .where(
            User.session_token_hash.is_not(None),
            User.session_expires > at,
            User.last_seen > _active_since(at),
        )
    )


# --- Cookie ---


def _cookie_options() -> dict:
    return {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "path": "/",
    }


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=settings.session_ttl_seconds, **_cookie_options()
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, **_cookie_options())
