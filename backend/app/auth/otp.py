"""One-time password flow: issuing codes (request-otp) and checking them (verify-otp)."""

from email_validator import EmailNotValidError, validate_email
from sqlalchemy.orm import Session

from app.auth.email import EmailSender, EmailSendError
from app.auth.models import User
from app.core import messages
from app.core.clock import now
from app.core.config import settings
from app.core.errors import ErrorCode, error
from app.core.security import generate_otp, hash_otp


def normalize_email(raw: str) -> str:
    """Validated, lowercase e-mail address, or `400 INVALID_EMAIL`."""
    try:
        email = validate_email(raw.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        raise error(ErrorCode.INVALID_EMAIL) from None

    domain = email.rpartition("@")[2]
    if settings.allowed_email_domains and domain not in settings.allowed_email_domains:
        raise error(ErrorCode.INVALID_EMAIL)
    return email


def clear_otp(user: User) -> None:
    user.otp_hash = None
    user.otp_expires = None
    user.otp_sent_at = None
    user.otp_attempts = 0


async def request_otp(db: Session, raw_email: str, sender: EmailSender) -> User:
    """Create the user if needed, store a new code and e-mail it.

    Raises `OTP_RATE_LIMITED` when a code was sent less than OTP_RESEND_SECONDS ago and
    `INTERNAL_ERROR` when the e-mail can't be delivered (the code is then discarded so the
    user can retry right away).
    """
    email = normalize_email(raw_email)
    current = now()

    user = db.get(User, email)
    if user is None:
        user = User(email=email)
        db.add(user)
    elif user.otp_sent_at is not None:
        wait = user.otp_sent_at + settings.otp_resend_seconds - current
        if wait > 0:
            raise error(ErrorCode.OTP_RATE_LIMITED, retry_after_seconds=wait)

    code = generate_otp()
    user.otp_hash = hash_otp(email, code)
    user.otp_expires = current + settings.otp_ttl_seconds
    user.otp_sent_at = current
    user.otp_attempts = 0
    # Commit before sending: an e-mailed code must always be one we can verify.
    db.commit()

    try:
        await sender.send_otp(email, code)
    except EmailSendError:
        clear_otp(user)
        db.commit()
        raise error(ErrorCode.INTERNAL_ERROR, message=messages.EMAIL_SEND_FAILED) from None
    return user
