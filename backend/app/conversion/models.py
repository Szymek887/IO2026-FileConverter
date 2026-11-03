"""Conversion jobs, their input files and results (data model from the requirements, §3).

    Job ──< InputFile          1–2 uploaded files, ordered by `position`
     └── Result ──< OutputFile  set when the job is done/error; outputs ordered by `index`

File paths are stored relative to `DATA_DIR` (see `storage.py`) and set to NULL once the
file has been deleted. Original file names are only stored here, never used as paths.
"""

import uuid
from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.conversion.formats import Category, Format
from app.core.clock import now
from app.core.db import Base


class JobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"


class ResultStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"


def _enum(enum_cls: type[StrEnum]) -> Enum:
    """Store a StrEnum as its value (`"mp3"`, not the member name `"MP3"`) in a VARCHAR."""
    return Enum(
        enum_cls,
        native_enum=False,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
        length=16,
    )


def _new_id() -> str:
    return str(uuid.uuid4())


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_email: Mapped[str] = mapped_column(
        ForeignKey("users.email", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[int] = mapped_column(default=now)
    target_format: Mapped[Format] = mapped_column(_enum(Format))
    status: Mapped[JobStatus] = mapped_column(
        _enum(JobStatus), default=JobStatus.QUEUED, index=True
    )
    started_at: Mapped[int | None]

    files: Mapped[list["InputFile"]] = relationship(
        back_populates="job",
        order_by="InputFile.position",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    result: Mapped["Result | None"] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="selectin"
    )


class InputFile(Base):
    __tablename__ = "input_files"
    __table_args__ = (UniqueConstraint("job_id", "position"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int]  # 0-based order in the upload
    name: Mapped[str] = mapped_column(String(255))  # sanitized original name, display only
    extension: Mapped[Format] = mapped_column(_enum(Format))
    category: Mapped[Category] = mapped_column(_enum(Category))
    size: Mapped[int]  # bytes
    path: Mapped[str | None] = mapped_column(String(255))  # relative to DATA_DIR

    job: Mapped[Job] = relationship(back_populates="files")


class Result(Base):
    __tablename__ = "results"

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    finished_at: Mapped[int] = mapped_column(default=now)
    status: Mapped[ResultStatus] = mapped_column(_enum(ResultStatus))
    message: Mapped[str] = mapped_column(Text)  # Polish, shown to the user as-is
    expires_at: Mapped[int | None]  # downloads return 410 afterwards; NULL on error
    purged: Mapped[bool] = mapped_column(default=False)  # outputs deleted by retention

    job: Mapped[Job] = relationship(back_populates="result")
    outputs: Mapped[list["OutputFile"]] = relationship(
        back_populates="result",
        order_by="OutputFile.index",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class OutputFile(Base):
    __tablename__ = "output_files"

    job_id: Mapped[str] = mapped_column(
        ForeignKey("results.job_id", ondelete="CASCADE"), primary_key=True
    )
    index: Mapped[int] = mapped_column(primary_key=True)  # = position of the input file
    name: Mapped[str] = mapped_column(String(255))  # download name, e.g. `nagranie.mp3`
    size: Mapped[int]  # bytes
    path: Mapped[str | None] = mapped_column(String(255))  # relative to DATA_DIR

    result: Mapped[Result] = relationship(back_populates="outputs")
