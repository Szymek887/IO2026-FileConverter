import asyncio

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from app.conversion import storage, upload
from app.conversion.formats import Format
from app.conversion.upload import receive_upload
from app.core.config import settings
from app.core.errors import AppError, ErrorCode, register_exception_handlers

JOB = "7f3a9c2e-4b1d-4e8a-9c3f-2a1b5d6e7f80"
BOUNDARY = "----testboundary7MA4YWxkTrZu0gW"
LIMIT = 1000  # MAX_FILE_SIZE used in these tests


@pytest.fixture(autouse=True)
def small_limits(monkeypatch):
    monkeypatch.setattr(settings, "max_file_size", LIMIT)
    monkeypatch.setattr(settings, "max_files_per_job", 2)


def part(name: str, data: bytes, filename: str | None = None, disposition: str | None = None):
    if disposition is None:
        disposition = f'form-data; name="{name}"'
        if filename is not None:
            disposition += f'; filename="{filename}"'
    head = f"--{BOUNDARY}\r\nContent-Disposition: {disposition}\r\n"
    if filename is not None or "filename" in disposition:
        head += "Content-Type: application/octet-stream\r\n"
    return head.encode("utf-8") + b"\r\n" + data + b"\r\n"


def body(*parts: bytes) -> bytes:
    return b"".join(parts) + f"--{BOUNDARY}--\r\n".encode()


class FakeRequest:
    """Feeds `data` in small chunks, so headers and data are split across chunks."""

    def __init__(self, data: bytes, chunk_size: int = 7, content_type: str | None = None):
        self.headers = Headers(
            {"content-type": content_type or f"multipart/form-data; boundary={BOUNDARY}"}
        )
        self.data = data
        self.chunk_size = chunk_size
        self.consumed = 0
        self.fail_after: int | None = None

    async def stream(self):
        for i in range(0, len(self.data), self.chunk_size):
            if self.fail_after is not None and self.consumed >= self.fail_after:
                raise ConnectionResetError("client went away")
            chunk = self.data[i : i + self.chunk_size]
            self.consumed += len(chunk)
            yield chunk


def receive(request) -> upload.UploadResult:
    return asyncio.run(receive_upload(request, JOB))


def receive_error(request) -> AppError:
    with pytest.raises(AppError) as exc_info:
        receive(request)
    assert not storage.upload_dir(JOB).exists(), "uploads must be removed on error"
    return exc_info.value


# --- success ---------------------------------------------------------------------------


@pytest.mark.parametrize("chunk_size", [1, 7, 65536])
def test_two_files_and_target(chunk_size):
    wav, flac = b"RIFF" + b"\x01" * 500, b"fLaC" + b"\x02" * 300
    request = FakeRequest(
        body(
            part("files", wav, "nagranie.wav"),
            part("files", flac, "muzyka.FLAC"),
            part("target_format", b"mp3"),
        ),
        chunk_size,
    )
    result = receive(request)

    assert result.target_format == "mp3"
    assert [(f.name, f.format, f.size) for f in result.files] == [
        ("nagranie.wav", Format.WAV, len(wav)),
        ("muzyka.FLAC", Format.FLAC, len(flac)),
    ]
    assert result.files[0].path == storage.upload_path(JOB, result.files[0].id, Format.WAV)
    assert result.files[0].path.read_bytes() == wav
    assert result.files[1].path.read_bytes() == flac


def test_target_before_files_and_exactly_at_limit():
    data = b"\xff" * LIMIT
    result = receive(
        FakeRequest(body(part("target_format", b" png "), part("files", data, "a.jpeg")))
    )
    assert result.target_format == "png"
    assert result.files[0].format is Format.JPG
    assert result.files[0].size == LIMIT


def test_missing_target_is_left_for_validation():
    result = receive(FakeRequest(body(part("files", b"x", "a.png"))))
    assert result.target_format is None


def test_no_files_is_left_for_validation():
    assert receive(FakeRequest(body(part("target_format", b"mp3")))).files == []


def test_empty_file_input_and_unknown_fields_are_ignored():
    result = receive(
        FakeRequest(
            body(
                part("files", b"", ""),  # <input type=file> with nothing selected
                part("comment", b"hello"),
                part("other", b"data", "other.exe"),
                part("files", b"text only, no filename"),
                part("files", b"x", "a.png"),
            )
        )
    )
    assert [f.name for f in result.files] == ["a.png"]


@pytest.mark.parametrize(
    ("disposition", "expected"),
    [
        ('form-data; name="files"; filename="zażółć gęślą.png"', "zażółć gęślą.png"),
        (
            'form-data; name="files"; filename="fallback.png"; '
            "filename*=UTF-8''za%C5%BC%C3%B3%C5%82%C4%87.png",
            "zażółć.png",
        ),
        ('form-data; name="files"; filename="C:\\fakepath\\photo.png"', "photo.png"),
        ('form-data; name="files"; filename="evil\u202egnp.exe.png"', "evilgnp.exe.png"),
    ],
)
def test_file_names(disposition, expected):
    result = receive(FakeRequest(body(part("files", b"x", disposition=disposition))))
    assert result.files[0].name == expected
    assert result.files[0].path.name == f"{result.files[0].id}.png"  # never the user's name


# --- errors ----------------------------------------------------------------------------


def test_file_too_large_is_rejected_and_body_drained():
    request = FakeRequest(
        body(part("files", b"x" * (LIMIT + 1), "film.mov"), part("files", b"y" * 500, "b.mov"))
    )
    exc = receive_error(request)
    assert exc.code is ErrorCode.FILE_TOO_LARGE
    assert exc.http_status == 413
    assert exc.details["file"] == "film.mov"
    assert "film.mov" in exc.message
    assert request.consumed == len(request.data)  # whole body read before answering


def test_draining_stops_at_cap(monkeypatch):
    monkeypatch.setattr(upload, "DRAIN_EXTRA_BYTES", 0)
    request = FakeRequest(body(part("files", b"x" * (5 * LIMIT), "a.mov")), chunk_size=100)
    receive_error(request)
    assert request.consumed < len(request.data)


def test_too_many_files():
    exc = receive_error(FakeRequest(body(*(part("files", b"x", f"{i}.png") for i in range(3)))))
    assert exc.code is ErrorCode.TOO_MANY_FILES
    assert exc.message == "Możesz przesłać maksymalnie 2 pliki naraz."


@pytest.mark.parametrize(
    "filename", ["dokument.pdf", "archive.tar.gz", "no_extension", "a.png.exe"]
)
def test_unsupported_format(filename):
    exc = receive_error(FakeRequest(body(part("files", b"x", filename))))
    assert exc.code is ErrorCode.UNSUPPORTED_FORMAT
    assert exc.http_status == 415
    assert exc.details["file"] == filename


def test_second_file_error_removes_first_file():
    exc = receive_error(
        FakeRequest(body(part("files", b"ok", "a.png"), part("files", b"x", "dokument.pdf")))
    )
    assert exc.code is ErrorCode.UNSUPPORTED_FORMAT


def test_target_too_long():
    exc = receive_error(FakeRequest(body(part("target_format", b"m" * 100))))
    assert exc.code is ErrorCode.VALIDATION_ERROR
    assert "target_format" in exc.details["fields"]


@pytest.mark.parametrize(
    "content_type",
    ["application/json", "multipart/form-data", "text/plain; boundary=x", ""],
)
def test_wrong_content_type(content_type):
    request = FakeRequest(b"{}", content_type=content_type)
    request.headers = Headers({"content-type": content_type})
    exc = receive_error(request)
    assert exc.code is ErrorCode.VALIDATION_ERROR


def test_truncated_body():
    data = body(part("files", b"x" * 100, "a.png"))
    exc = receive_error(FakeRequest(data[: len(data) // 2]))
    assert exc.code is ErrorCode.VALIDATION_ERROR


def test_client_disconnect_removes_files():
    request = FakeRequest(body(part("files", b"x" * 900, "a.png")), chunk_size=100)
    request.fail_after = 500
    with pytest.raises(ConnectionResetError):
        receive(request)
    assert not storage.upload_dir(JOB).exists()


# --- through a real HTTP request -------------------------------------------------------


@pytest.fixture
def http():
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/upload")
    async def endpoint(request: Request):
        result = await receive_upload(request, JOB)
        return {
            "target_format": result.target_format,
            "files": [{"name": f.name, "format": f.format, "size": f.size} for f in result.files],
        }

    with TestClient(app) as client:
        yield client


def test_http_upload(http):
    response = http.post(
        "/upload",
        files=[("files", ("zdjęcie.HEIC", b"a" * 10)), ("files", ("b.jpg", b"b" * 20))],
        data={"target_format": "png"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "target_format": "png",
        "files": [
            {"name": "zdjęcie.HEIC", "format": "heic", "size": 10},
            {"name": "b.jpg", "format": "jpg", "size": 20},
        ],
    }


def test_http_too_large_returns_contract_error(http):
    response = http.post("/upload", files=[("files", ("film.mov", b"x" * (LIMIT + 1)))])
    assert response.status_code == 413
    assert response.json() == {
        "status": "error",
        "code": "FILE_TOO_LARGE",
        "message": "Plik „film.mov” przekracza maksymalny rozmiar 0 MB.",
        "details": {"file": "film.mov", "limit_mb": 0},
    }
    assert not storage.upload_dir(JOB).exists()
