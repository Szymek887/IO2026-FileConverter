import threading
from pathlib import Path

import pytest
from sqlalchemy import ForeignKey, inspect, make_url, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from app.core import db as db_module
from app.core.config import settings
from app.core.db import Base, create_db_engine, database_url, get_db, init_db, sqlite_url


class Parent(Base):
    __tablename__ = "test_parent"
    id: Mapped[int] = mapped_column(primary_key=True)


class Child(Base):
    __tablename__ = "test_child"
    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("test_parent.id"))


@pytest.fixture(scope="module", autouse=True)
def drop_test_models():
    """Keep the test-only tables out of the shared metadata for other test modules."""
    yield
    for table in (Child.__table__, Parent.__table__):
        Base.metadata.remove(table)


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    engine = create_db_engine(sqlite_url(tmp_path / "nested" / "app.db"))
    yield engine
    engine.dispose()


def test_init_db_creates_directories_and_tables(engine, tmp_path):
    init_db(engine)

    assert (tmp_path / "data").is_dir()
    assert (tmp_path / "nested" / "app.db").is_file()
    assert {"test_parent", "test_child"} <= set(inspect(engine).get_table_names())


def test_sqlite_pragmas_are_set(engine):
    init_db(engine)
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_foreign_keys_are_enforced(engine):
    init_db(engine)
    with Session(engine) as session:
        session.add(Child(id=1, parent_id=999))
        with pytest.raises(IntegrityError):
            session.commit()


def test_session_usable_from_another_thread(engine):
    init_db(engine)
    session = sessionmaker(bind=engine)()
    session.add(Parent(id=1))
    session.commit()

    errors = []

    def read():
        try:
            assert session.get(Parent, 1) is not None
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=read)
    thread.start()
    thread.join()
    session.close()
    assert errors == []


def test_get_db_yields_session_and_closes_it(engine, monkeypatch):
    init_db(engine)
    monkeypatch.setattr(db_module, "SessionLocal", sessionmaker(bind=engine))

    dependency = get_db()
    session = next(dependency)
    session.add(Parent(id=1))
    dependency.close()  # what FastAPI does after the request

    with Session(engine) as fresh:
        assert fresh.get(Parent, 1) is None  # uncommitted work was rolled back


@pytest.mark.parametrize(
    "path",
    [
        r"C:\Users\Jan Kowalski\AppData\Local\Temp\data\app.db",
        r"data\app.db",
        "/tmp/100% sure?/#1/app.db",
    ],
)
def test_sqlite_url_keeps_any_path_intact(path):
    assert make_url(sqlite_url(Path(path))).database == str(Path(path))


def test_database_url_defaults_to_sqlite_file_in_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    assert make_url(database_url()).database == str(tmp_path / "data" / "app.db")


def test_explicit_database_url_is_used(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "sqlite:///:memory:")
    assert database_url() == "sqlite:///:memory:"


def test_engine_works_with_special_characters_in_path(tmp_path):
    engine = create_db_engine(sqlite_url(tmp_path / "100% sure" / "#1 data" / "app.db"))
    init_db(engine)
    assert (tmp_path / "100% sure" / "#1 data" / "app.db").is_file()
    engine.dispose()
