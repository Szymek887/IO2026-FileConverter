from typing import Annotated

from fastapi import Cookie, Depends
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.db import get_db
from app.core.errors import ErrorCode, error

SESSION_COOKIE = "session"


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> User:
    """Return the logged-in user or raise `401 UNAUTHENTICATED`.

    Stub until sessions are implemented (A12): every request is unauthenticated.
    Tests use the `auth_client` fixture, which overrides this dependency.
    """
    raise error(ErrorCode.UNAUTHENTICATED)


CurrentUser = Annotated[User, Depends(get_current_user)]
