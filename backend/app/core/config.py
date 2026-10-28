"""Application settings loaded from environment variables and an optional `.env` file.

Variable names are case-insensitive (`MAX_FILE_SIZE` -> `settings.max_file_size`).
List values are given as JSON, e.g. `CORS_ORIGINS=["http://localhost:5173"]`.
See `.env.example` for all keys.
"""

from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "dev-insecure-secret-key-change-me"
MIN_PROD_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["dev", "prod"] = "dev"
    secret_key: str = DEFAULT_SECRET_KEY

    # Storage
    data_dir: Path = Path("./data")
    database_url: str = ""  # empty -> SQLite file inside data_dir

    # Upload / conversion limits
    max_file_size: int = 250 * 1024 * 1024
    max_files_per_job: int = 2
    output_retention_seconds: int = 24 * 60 * 60

    # Concurrent users
    max_active_users: int = 10
    active_window_seconds: int = 15 * 60

    # One-time passwords
    otp_ttl_seconds: int = 10 * 60
    otp_resend_seconds: int = 60
    otp_max_attempts: int = 5

    # Sessions
    session_ttl_seconds: int = 24 * 60 * 60
    cookie_secure: bool = True

    # HTTP
    cors_origins: list[str] = ["http://localhost:5173"]

    # E-mail
    email_backend: Literal["console", "smtp"] = "console"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    allowed_email_domains: list[str] = []  # empty -> any domain

    @model_validator(mode="after")
    def _fill_defaults_and_validate(self) -> "Settings":
        if not self.database_url:
            self.database_url = f"sqlite:///{self.data_dir / 'app.db'}"
        self.allowed_email_domains = [d.strip().lower() for d in self.allowed_email_domains]

        if self.email_backend == "smtp" and not (self.smtp_host and self.smtp_from):
            raise ValueError("EMAIL_BACKEND=smtp requires SMTP_HOST and SMTP_FROM")

        if self.env == "prod":
            if (
                self.secret_key == DEFAULT_SECRET_KEY
                or len(self.secret_key) < MIN_PROD_SECRET_KEY_LENGTH
            ):
                raise ValueError(
                    f"ENV=prod requires SECRET_KEY of at least "
                    f"{MIN_PROD_SECRET_KEY_LENGTH} characters (not the default)"
                )
            if self.email_backend == "console":
                raise ValueError("ENV=prod requires EMAIL_BACKEND=smtp")
            if not self.cookie_secure:
                raise ValueError("ENV=prod requires COOKIE_SECURE=true")
        return self


settings = Settings()
