"""Database engine, session factory and the declarative `Base` shared by all models.

- Request handlers get a session via the `get_db` dependency and commit explicitly.
- Background threads (conversion worker) open their own: `with SessionLocal() as db: ...`.
- Model modules must be imported before `init_db()` so their tables get created.
"""

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    # WAL lets the worker write while request handlers read.
    cursor.execute("PRAGMA journal_mode=WAL")
    # SQLite ignores foreign keys unless enabled per connection.
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_db_engine(url: str) -> Engine:
    if not url.startswith("sqlite"):
        return create_engine(url)
    # Connections are shared between FastAPI's threadpool and the worker threads.
    engine = create_engine(url, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _set_sqlite_pragmas)
    return engine


engine = create_db_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, closed afterwards (uncommitted work is
    rolled back)."""
    with SessionLocal() as db:
        yield db


def init_db(bind: Engine | None = None) -> None:
    """Create the data directory and all tables. Called once on application startup."""
    bind = bind or engine
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    database = bind.url.database
    if bind.url.get_backend_name() == "sqlite" and database and database != ":memory:":
        Path(database).parent.mkdir(parents=True, exist_ok=True)

    Base.metadata.create_all(bind)
