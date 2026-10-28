"""Shared fixtures.

- `client`: TestClient for a fresh app with its own temporary DATA_DIR and SQLite database.
- `auth_client`: same, but every request is authenticated as `user`.
- `db`: a session on the test database (commit to make data visible to the app).
- `clock`: frozen time you can move with `clock.advance(seconds)`.
- `outbox`: captures login codes "sent" by the app instead of e-mailing/logging them.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.auth.email import get_email_sender
from app.auth.models import User
from app.core import clock as clock_module
from app.core import db as db_module
from app.core.config import settings
from app.main import create_app

TEST_EMAIL = "test@example.com"
FROZEN_AT = 1_793_102_400  # 2026-10-27 12:00 UTC


@pytest.fixture(autouse=True)
def test_database(tmp_path, monkeypatch) -> Iterator[None]:
    """Point DATA_DIR and the database at a temporary directory for every test."""
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    engine = db_module.create_db_engine(db_module.sqlite_url(data_dir / "app.db"))
    original_engine = db_module.engine
    monkeypatch.setattr(db_module, "engine", engine)
    # Rebind the shared sessionmaker so code that imported SessionLocal also uses the test DB.
    db_module.SessionLocal.configure(bind=engine)
    db_module.init_db(engine)
    yield
    db_module.SessionLocal.configure(bind=original_engine)
    engine.dispose()


@pytest.fixture
def db() -> Iterator[Session]:
    with db_module.SessionLocal() as session:
        yield session


class FrozenClock:
    def __init__(self, timestamp: int) -> None:
        self.set(timestamp)

    def now(self) -> int:
        return clock_module.now()

    def set(self, timestamp: int) -> None:
        clock_module.freeze(timestamp)

    def advance(self, seconds: int) -> None:
        clock_module.freeze(clock_module.now() + seconds)


@pytest.fixture
def clock() -> Iterator[FrozenClock]:
    yield FrozenClock(FROZEN_AT)
    clock_module.unfreeze()


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:  # `with` runs the lifespan (startup/shutdown)
        yield test_client


@pytest.fixture
def user(db: Session) -> User:
    user = User(email=TEST_EMAIL)
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def auth_client(app: FastAPI, user: User) -> Iterator[TestClient]:
    """Client whose requests are all authenticated as `user` (bypasses the session cookie)."""
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class Outbox:
    """Records login codes sent by the app: `outbox.sent == [(email, code), ...]`."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_otp(self, email: str, code: str) -> None:
        self.sent.append((email, code))

    def last_code(self, email: str) -> str:
        return next(code for to, code in reversed(self.sent) if to == email)


@pytest.fixture
def outbox(app: FastAPI) -> Outbox:
    outbox = Outbox()
    app.dependency_overrides[get_email_sender] = lambda: outbox
    return outbox
