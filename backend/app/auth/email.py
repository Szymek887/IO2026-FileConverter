"""Sending login codes by e-mail.

`EMAIL_BACKEND=console` logs the code instead of sending it (development).
`EMAIL_BACKEND=smtp` sends a real e-mail. Endpoints get the sender via the
`get_email_sender` dependency, which tests override to capture sent codes.
"""

import logging
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Protocol

import aiosmtplib

from app.core import messages
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailSendError(Exception):
    """The e-mail could not be delivered to the SMTP server."""


class EmailSender(Protocol):
    async def send_otp(self, email: str, code: str) -> None: ...


def build_otp_message(email: str, code: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = email
    message["Subject"] = messages.OTP_EMAIL_SUBJECT
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=settings.smtp_from.rpartition("@")[2] or None)
    message.set_content(
        messages.OTP_EMAIL_BODY.format(code=code, minutes=settings.otp_ttl_seconds // 60),
        cte="quoted-printable",
    )
    return message


class ConsoleEmailSender:
    async def send_otp(self, email: str, code: str) -> None:
        logger.info("Login code for %s: %s (EMAIL_BACKEND=console, no e-mail sent)", email, code)


class SmtpEmailSender:
    async def send_otp(self, email: str, code: str) -> None:
        try:
            await aiosmtplib.send(
                build_otp_message(email, code),
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user or None,
                password=settings.smtp_password or None,
                use_tls=settings.smtp_tls == "tls",
                start_tls=settings.smtp_tls == "starttls",
                timeout=settings.smtp_timeout_seconds,
            )
        except (aiosmtplib.SMTPException, OSError, TimeoutError) as exc:
            # Never log the code itself in production.
            logger.error("Sending login code to %s failed: %r", email, exc)
            raise EmailSendError(str(exc)) from exc


def get_email_sender() -> EmailSender:
    if settings.email_backend == "smtp":
        return SmtpEmailSender()
    return ConsoleEmailSender()
