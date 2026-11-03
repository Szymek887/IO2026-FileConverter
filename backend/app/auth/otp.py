"""One-time password flow: issuing codes (request-otp) and checking them (verify-otp)."""

from email_validator import EmailNotValidError, validate_email
from sqlalchemy.orm import Session

from app.auth.email import EmailSender, EmailSendError
from app.auth.models import User
from app.auth.sessions import count_active_users, create_session, is_active
from app.core import messages
from app.core.clock import now
from app.core.config import settings
from app.core.errors import ErrorCode, error
from app.core.security import generate_otp, hash_otp, verify_otp


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
    """Invalidate the pending code. `otp_sent_at` is kept so the resend limit still applies
    (otherwise a locked-out attacker could request a new code right away and keep guessing)."""
    user.otp_hash = None
    user.otp_expires = None
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
        user.otp_sent_at = None  # nothing was delivered, allow an immediate retry
        db.commit()
        raise error(ErrorCode.INTERNAL_ERROR, message=messages.EMAIL_SEND_FAILED) from None
    return user


def verify_code(db: Session, raw_email: str, code: str) -> tuple[User, str]:
    """Check the code and log the user in. Returns the user and the new session token.

    - no pending / expired / already used code -> `401 OTP_EXPIRED`
    - wrong code -> `401 INVALID_OTP`; the OTP_MAX_ATTEMPTS-th wrong code invalidates it
      -> `429 TOO_MANY_ATTEMPTS`
    - correct code but MAX_ACTIVE_USERS others are active -> `503 USER_LIMIT_REACHED`;
      the code is not consumed, so the user can retry with it later
    """
    email = raw_email.strip().lower()
    current = now()

    user = db.get(User, email)
    if user is None or user.otp_hash is None or (user.otp_expires or 0) <= current:
        raise error(ErrorCode.OTP_EXPIRED)

    if not verify_otp(email, code, user.otp_hash):
        user.otp_attempts += 1
        locked = user.otp_attempts >= settings.otp_max_attempts
        if locked:
            clear_otp(user)
        db.commit()
        raise error(ErrorCode.TOO_MANY_ATTEMPTS if locked else ErrorCode.INVALID_OTP)

    limit = settings.max_active_users
    if not is_active(user, current) and count_active_users(db, current) >= limit:
        raise error(ErrorCode.USER_LIMIT_REACHED, format_args={"limit": limit})

    clear_otp(user)
    token = create_session(user, current)
    db.commit()
    return user, token
