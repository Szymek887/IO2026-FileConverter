import threading

import pytest
from sqlalchemy import ForeignKey, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from app.core import db as db_module
from app.core.config import settings
from app.core.db import Base, create_db_engine, get_db, init_db


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
    engine = create_db_engine(f"sqlite:///{tmp_path / 'nested' / 'app.db'}")
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
