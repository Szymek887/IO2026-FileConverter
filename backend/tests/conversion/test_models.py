import uuid

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError, StatementError

from app.conversion.formats import Category, Format
from app.conversion.models import InputFile, Job, JobStatus, OutputFile, Result, ResultStatus
from app.core import db as db_module


def make_job(user, n_files=2, **kwargs) -> Job:
    job = Job(user_email=user.email, target_format=Format.MP3, **kwargs)
    names = ["nagranie.wav", "muzyka.flac"]
    for position in reversed(range(n_files)):  # added out of order on purpose
        fmt = Format.WAV if position == 0 else Format.FLAC
        job.files.append(
            InputFile(
                position=position,
                name=names[position],
                extension=fmt,
                category=Category.AUDIO,
                size=1000 + position,
                path=f"uploads/x/{position}.{fmt}",
            )
        )
    return job


def test_tables_are_created_on_startup():
    tables = set(inspect(db_module.engine).get_table_names())
    assert {"jobs", "input_files", "results", "output_files"} <= tables


def test_job_defaults(db, user, clock):
    job = make_job(user)
    db.add(job)
    db.commit()

    assert uuid.UUID(job.id).version == 4
    assert job.status is JobStatus.QUEUED
    assert job.created_at == clock.now()
    assert job.started_at is None
    assert job.result is None
    assert all(uuid.UUID(f.id).version == 4 for f in job.files)


def test_enums_round_trip_as_values(db, user):
    db.add(make_job(user, status=JobStatus.PROCESSING))
    db.commit()
    db.expire_all()

    job = db.scalars(select(Job)).one()
    assert job.target_format is Format.MP3
    assert job.status is JobStatus.PROCESSING
    assert job.files[0].category is Category.AUDIO
    # Stored as the lowercase value, as used in the API contract.
    row = db.execute(text("SELECT target_format, status FROM jobs")).one()
    assert tuple(row) == ("mp3", "processing")


def test_invalid_enum_value_is_rejected(db, user):
    db.add(Job(user_email=user.email, target_format="exe"))
    with pytest.raises(StatementError):
        db.commit()


def test_files_are_ordered_by_position(db, user):
    db.add(make_job(user))
    db.commit()
    db.expire_all()

    job = db.scalars(select(Job)).one()
    assert [f.position for f in job.files] == [0, 1]
    assert [f.name for f in job.files] == ["nagranie.wav", "muzyka.flac"]


def test_duplicate_position_is_rejected(db, user):
    job = make_job(user, n_files=1)
    job.files.append(
        InputFile(position=0, name="b.wav", extension=Format.WAV, category=Category.AUDIO, size=1)
    )
    db.add(job)
    with pytest.raises(IntegrityError):
        db.commit()


def test_job_requires_existing_user(db):
    db.add(Job(user_email="nobody@example.com", target_format=Format.MP3))
    with pytest.raises(IntegrityError):
        db.commit()


def test_result_with_outputs(db, user, clock):
    job = make_job(user, status=JobStatus.DONE)
    job.result = Result(
        status=ResultStatus.SUCCESS,
        message="Konwersja zakończona pomyślnie.",
        expires_at=clock.now() + 86400,
        outputs=[
            OutputFile(index=1, name="muzyka.mp3", size=20, path="outputs/x/1.mp3"),
            OutputFile(index=0, name="nagranie.mp3", size=10, path="outputs/x/0.mp3"),
        ],
    )
    db.add(job)
    db.commit()
    db.expire_all()

    result = db.scalars(select(Job)).one().result
    assert result.finished_at == clock.now()
    assert result.status is ResultStatus.SUCCESS
    assert not result.purged
    assert [o.index for o in result.outputs] == [0, 1]
    assert result.outputs[0].name == "nagranie.mp3"


def test_deleting_job_deletes_everything(db, user):
    job = make_job(user)
    job.result = Result(
        status=ResultStatus.ERROR,
        message="Nie udało się przekonwertować pliku „x.wav”.",
        outputs=[OutputFile(index=0, name="x.mp3", size=1)],
    )
    db.add(job)
    db.commit()

    db.delete(job)
    db.commit()
    for model in (Job, InputFile, Result, OutputFile):
        assert db.scalars(select(model)).all() == []
