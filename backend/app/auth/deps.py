from typing import Annotated

from fastapi import Cookie, Depends, Response
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.sessions import SESSION_COOKIE, find_session_user, refresh_session, set_session_cookie
from app.core.clock import now
from app.core.db import get_db
from app.core.errors import ErrorCode, error


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    response: Response,
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> User:
    """Return the logged-in user or raise `401 UNAUTHENTICATED`.

    Also slides the session expiry forward. The refreshed cookie is sent with JSON responses;
    endpoints returning their own Response (file downloads) only extend it in the database,
    and the cookie catches up on the next JSON request.
    """
    current = now()
    user = find_session_user(db, session, current) if session else None
    if user is None:
        raise error(ErrorCode.UNAUTHENTICATED)

    if refresh_session(user, current):
        db.commit()
        set_session_cookie(response, session)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
