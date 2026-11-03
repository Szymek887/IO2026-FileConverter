"""Streaming receiver for `POST /api/jobs` (multipart/form-data with `files` and `target_format`).

FastAPI's `UploadFile` reads the whole body before the endpoint runs; here each chunk is
parsed as it arrives and written straight to `DATA_DIR/uploads/{job_id}/`, so the checks
below fire as early as possible (validation rules 1–4 of the plan):

1. Content-Type must be multipart/form-data with a boundary   -> 400 VALIDATION_ERROR
2. a 3rd file part appears (checked at its headers)            -> 400 TOO_MANY_FILES
3. file extension unsupported (checked at its headers)         -> 415 UNSUPPORTED_FORMAT
4. a file grows past MAX_FILE_SIZE (checked while streaming)   -> 413 FILE_TOO_LARGE

After the first error nothing more is written and the rest of the body is drained (read and
discarded): answering while the browser is still uploading resets the connection, and the
user would see a network error instead of our message. Content checks, NO_FILES and the
target format are validated afterwards (`validation.py`).
"""

import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Protocol
from urllib.parse import unquote

from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import MultipartParser, parse_options_header
from starlette.datastructures import Headers

from app.conversion import storage
from app.conversion.formats import Format, format_from_filename
from app.core.config import settings
from app.core.errors import AppError, ErrorCode, error

FILES_FIELD = "files"
TARGET_FIELD = "target_format"
MAX_TARGET_LENGTH = 32  # bytes; longer values are not a format name
DRAIN_EXTRA_BYTES = 10 * 1024 * 1024  # multipart overhead allowed on top of the file limits

# RFC 5987 `filename*=UTF-8''...`, which `parse_options_header` ignores.
_EXTENDED_FILENAME = re.compile(rb"filename\*\s*=\s*([\w!#$&+.^`|~-]+)'[^']*'([^;\s]+)", re.I)


class UploadRequest(Protocol):
    """The part of `starlette.requests.Request` the receiver needs (tests pass fakes)."""

    @property
    def headers(self) -> Headers: ...

    def stream(self) -> AsyncIterator[bytes]: ...


@dataclass
class StagedFile:
    """A received file, already on disk at `path` (`uploads/{job_id}/{id}.{format}`)."""

    id: str
    name: str  # display name (sanitized), used in messages and output names
    format: Format
    path: Path
    size: int = 0


@dataclass
class UploadResult:
    files: list[StagedFile] = field(default_factory=list)  # in upload order
    target_format: str | None = None  # raw value; validated later


async def receive_upload(request: UploadRequest, job_id: str) -> UploadResult:
    """Stream the multipart body to disk. On any error the job's upload directory is
    removed and an `AppError` is raised (after draining the body)."""
    boundary = _boundary(request.headers.get("content-type"))
    receiver = _Receiver(job_id)
    parser = MultipartParser(boundary, receiver.callbacks())
    failure: AppError | None = None
    received = 0
    drain_limit = settings.max_files_per_job * settings.max_file_size + DRAIN_EXTRA_BYTES

    try:
        async for chunk in request.stream():
            received += len(chunk)
            if failure is None:
                try:
                    parser.write(chunk)
                except AppError as exc:
                    failure = exc
                except MultipartParseError:
                    failure = error(ErrorCode.VALIDATION_ERROR, fields={"body": "malformed"})
                if failure is not None:
                    receiver.discard()
            elif received > drain_limit:
                break  # stop draining absurdly large bodies; the client may see a reset
        if failure is None and not receiver.finished:
            failure = error(ErrorCode.VALIDATION_ERROR, fields={"body": "incomplete"})
            receiver.discard()
    except BaseException:  # client disconnected, cancelled, disk full, ...
        receiver.discard()
        raise

    if failure is not None:
        raise failure
    return receiver.result


def _boundary(content_type: str | None) -> bytes:
    mime, params = parse_options_header(content_type)
    boundary = params.get(b"boundary")
    if mime != b"multipart/form-data" or not boundary:
        raise error(ErrorCode.VALIDATION_ERROR, fields={"body": "expected multipart/form-data"})
    return boundary


def _filename(disposition: bytes, params: dict[bytes, bytes]) -> str | None:
    """`filename*` (RFC 5987) if present, else `filename`; `None` for non-file fields."""
    if match := _EXTENDED_FILENAME.search(disposition):
        charset, value = match.groups()
        try:
            return unquote(value.decode("ascii"), encoding=charset.decode(), errors="strict")
        except (LookupError, UnicodeDecodeError):
            pass
    raw = params.get(b"filename")
    if raw is None:
        return None
    try:
        return raw.decode("utf-8")  # what browsers send
    except UnicodeDecodeError:
        return raw.decode("latin-1")


class _Receiver:
    """Multipart parser callbacks: tracks the current part and writes file data to disk."""

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self.result = UploadResult()
        self.finished = False
        self._file_count = 0
        self._header_field = b""
        self._header_value = b""
        self._headers: dict[bytes, bytes] = {}
        self._kind: str | None = None  # "file", "target" or None (part is ignored)
        self._current: StagedFile | None = None
        self._handle: BinaryIO | None = None
        self._target = bytearray()

    def callbacks(self) -> dict:
        return {
            "on_part_begin": self._on_part_begin,
            "on_header_field": self._on_header_field,
            "on_header_value": self._on_header_value,
            "on_header_end": self._on_header_end,
            "on_headers_finished": self._on_headers_finished,
            "on_part_data": self._on_part_data,
            "on_part_end": self._on_part_end,
            "on_end": self._on_end,
        }

    def discard(self) -> None:
        """Close the open file and delete everything received for this job."""
        if self._handle is not None:
            self._handle.close()
            self._handle = None
        storage.remove_uploads(self.job_id)
        self.result = UploadResult()

    # --- headers -------------------------------------------------------------------------

    def _on_part_begin(self) -> None:
        self._headers = {}
        self._kind = None

    def _on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._header_field += data[start:end]

    def _on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._header_value += data[start:end]

    def _on_header_end(self) -> None:
        self._headers[self._header_field.lower()] = self._header_value
        self._header_field = self._header_value = b""

    def _on_headers_finished(self) -> None:
        disposition = self._headers.get(b"content-disposition", b"")
        _, params = parse_options_header(disposition)
        name = params.get(b"name", b"").decode("utf-8", errors="replace")
        filename = _filename(disposition, params)

        if name == TARGET_FIELD and filename is None:
            self._kind = "target"
            self._target.clear()  # the last value wins
        elif name == FILES_FIELD and filename:  # an empty filename = no file chosen
            self._kind = "file"
            self._start_file(filename)

    def _start_file(self, filename: str) -> None:
        self._file_count += 1
        if self._file_count > settings.max_files_per_job:
            raise error(ErrorCode.TOO_MANY_FILES, format_args={"limit": settings.max_files_per_job})

        display = storage.display_name(filename)
        fmt = format_from_filename(filename)
        if fmt is None:
            raise error(ErrorCode.UNSUPPORTED_FORMAT, file=display)

        file_id = str(uuid.uuid4())
        path = storage.upload_path(self.job_id, file_id, fmt)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._current = StagedFile(id=file_id, name=display, format=fmt, path=path)
        self._handle = path.open("wb")

    # --- body ----------------------------------------------------------------------------

    def _on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._kind == "file":
            assert self._current is not None and self._handle is not None
            self._current.size += end - start
            if self._current.size > settings.max_file_size:
                raise error(
                    ErrorCode.FILE_TOO_LARGE,
                    file=self._current.name,
                    format_args={"limit_mb": settings.max_file_size // (1024 * 1024)},
                )
            self._handle.write(data[start:end])
        elif self._kind == "target":
            self._target += data[start:end]
            if len(self._target) > MAX_TARGET_LENGTH:
                raise error(ErrorCode.VALIDATION_ERROR, fields={TARGET_FIELD: "too long"})

    def _on_part_end(self) -> None:
        if self._kind == "file":
            assert self._current is not None and self._handle is not None
            self._handle.close()
            self._handle = None
            self.result.files.append(self._current)
            self._current = None
        elif self._kind == "target":
            self.result.target_format = self._target.decode("utf-8", errors="replace").strip()

    def _on_end(self) -> None:
        self.finished = True
