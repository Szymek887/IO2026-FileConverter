import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_SECRET_KEY, Settings

PROD_SECRET = "x" * 32
SMTP = {
    "email_backend": "smtp",
    "smtp_host": "smtp.example.com",
    "smtp_from": "noreply@example.com",
}


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Ignore the developer's shell environment so defaults are tested."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def make(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def test_defaults_match_requirements():
    s = make()
    assert s.env == "dev"
    assert s.max_file_size == 262_144_000
    assert s.max_files_per_job == 2
    assert s.max_active_users == 10
    assert s.otp_ttl_seconds == 600
    assert s.email_backend == "console"


def test_reads_environment_variables(monkeypatch):
    monkeypatch.setenv("MAX_ACTIVE_USERS", "3")
    monkeypatch.setenv("CORS_ORIGINS", '["http://a.test", "http://b.test"]')
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", '[" AGH.edu.pl "]')
    s = make()
    assert s.max_active_users == 3
    assert s.cors_origins == ["http://a.test", "http://b.test"]
    assert s.allowed_email_domains == ["agh.edu.pl"]


def test_smtp_backend_requires_host_and_sender():
    with pytest.raises(ValidationError, match="SMTP_HOST"):
        make(email_backend="smtp")


def test_valid_prod_config():
    s = make(env="prod", secret_key=PROD_SECRET, **SMTP)
    assert s.env == "prod"


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"secret_key": DEFAULT_SECRET_KEY}, "SECRET_KEY"),
        ({"secret_key": "too-short"}, "SECRET_KEY"),
        ({"email_backend": "console"}, "EMAIL_BACKEND"),
        ({"cookie_secure": False}, "COOKIE_SECURE"),
    ],
)
def test_prod_rejects_unsafe_config(overrides, error):
    kwargs = {"env": "prod", "secret_key": PROD_SECRET, **SMTP, **overrides}
    with pytest.raises(ValidationError, match=error):
        make(**kwargs)
