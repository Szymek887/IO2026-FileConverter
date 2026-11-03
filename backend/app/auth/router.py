from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy.orm import Session

from app.auth import otp
from app.auth.deps import CurrentUser
from app.auth.email import EmailSender, get_email_sender
from app.auth.schemas import RequestOtpRequest, RequestOtpResponse, SessionInfo, VerifyOtpRequest
from app.auth.sessions import (
    SESSION_COOKIE,
    clear_session_cookie,
    end_session,
    find_session_user,
    set_session_cookie,
)
from app.core import messages
from app.core.clock import now
from app.core.config import settings
from app.core.db import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post("/request-otp", status_code=202)
async def request_otp(
    body: RequestOtpRequest,
    db: DbSession,
    sender: Annotated[EmailSender, Depends(get_email_sender)],
) -> RequestOtpResponse:
    """Send a 6-digit one-time login code to the e-mail address."""
    user = await otp.request_otp(db, body.email, sender)
    return RequestOtpResponse(
        message=messages.OTP_SENT.format(email=user.email),
        otp_expires=user.otp_expires,
        resend_available_in=settings.otp_resend_seconds,
    )


@router.post("/verify-otp")
def verify_otp(body: VerifyOtpRequest, db: DbSession, response: Response) -> SessionInfo:
    """Check the code and start a session (sets the `session` cookie)."""
    user, token = otp.verify_code(db, body.email, body.code)
    set_session_cookie(response, token)
    return SessionInfo(email=user.email, session_expires=user.session_expires)


@router.get("/me")
def me(user: CurrentUser) -> SessionInfo:
    """Current session; `401 UNAUTHENTICATED` when not logged in."""
    return SessionInfo(email=user.email, session_expires=user.session_expires)


@router.post("/logout", status_code=204)
def logout(
    db: DbSession,
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Response:
    """End the session. Idempotent: also succeeds without a valid session."""
    user = find_session_user(db, session, now()) if session else None
    if user is not None:
        end_session(user)
        db.commit()
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response
