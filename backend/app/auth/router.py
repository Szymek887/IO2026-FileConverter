from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import otp
from app.auth.email import EmailSender, get_email_sender
from app.auth.schemas import RequestOtpRequest, RequestOtpResponse
from app.core import messages
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
