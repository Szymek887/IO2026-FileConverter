from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.db import Base


class User(Base):
    """A user is created on the first login code request. The fields follow the data model
    from the requirements: one pending login code and one active session per user."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), primary_key=True)  # stored lowercase
    created_at: Mapped[int] = mapped_column(default=now)

    # Pending one-time password (HMAC of email + code)
    otp_hash: Mapped[str | None]
    otp_expires: Mapped[int | None]
    otp_sent_at: Mapped[int | None]
    otp_attempts: Mapped[int] = mapped_column(default=0)

    # Active session (SHA-256 of the cookie token)
    session_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    session_expires: Mapped[int | None]
    last_seen: Mapped[int | None]
