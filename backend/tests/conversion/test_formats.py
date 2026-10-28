import pytest

from app.conversion.formats import (
    CATEGORY_OF,
    MIME_TYPES,
    Category,
    Format,
    allowed_targets,
    can_convert,
    format_from_filename,
    parse_format,
)

# Example response of `GET /api/formats` from docs/api-contract.md §4.
CONTRACT_FORMATS_RESPONSE = {
    "max_file_size": 262144000,
    "max_files_per_job": 2,
    "categories": [
        {"id": "audio", "label": "Audio", "formats": ["flac", "mp3", "wav"]},
        {"id": "video", "label": "Wideo", "formats": ["gif", "mp4", "mov"]},
        {"id": "image", "label": "Obraz", "formats": ["jpg", "png", "heic"]},
    ],
    "conversions": {
        "flac": ["mp3", "wav"],
        "mp3": ["flac", "wav"],
        "wav": ["flac", "mp3"],
        "gif": ["mp4", "mov"],
        "mp4": ["gif", "mov"],
        "mov": ["gif", "mp4"],
        "jpg": ["png", "heic"],
        "png": ["jpg", "heic"],
        "heic": ["jpg", "png"],
    },
    "extension_aliases": {"jpeg": "jpg", "heif": "heic"},
}


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("nagranie.wav", Format.WAV),
        ("FILM.MOV", Format.MOV),
        ("zdjęcie.Jpeg", Format.JPG),
        ("photo.HEIF", Format.HEIC),
        ("my.holiday.photo.png", Format.PNG),
        ("C:\\fakepath\\clip.mp4", Format.MP4),
        ("folder/song.flac", Format.FLAC),
        (".gif", Format.GIF),
    ],
)
def test_format_from_filename(filename, expected):
    assert format_from_filename(filename) is expected


@pytest.mark.parametrize(
    "filename",
    ["dokument.pdf", "notes.txt", "archive.tar.gz", "no_extension", "trailing.", "", "dir.png/"],
)
def test_format_from_filename_unsupported(filename):
    assert format_from_filename(filename) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [("mp3", Format.MP3), (" PNG ", Format.PNG), ("jpeg", Format.JPG), ("pdf", None), ("", None)],
)
def test_parse_format(value, expected):
    assert parse_format(value) is expected


def test_every_format_has_category_and_mime_type():
    assert set(CATEGORY_OF) == set(Format)
    assert set(MIME_TYPES) == set(Format)


@pytest.mark.parametrize("source", list(Format))
def test_allowed_targets_are_same_category_without_source(source):
    targets = allowed_targets(source)
    assert len(targets) == 2
    assert source not in targets
    assert all(CATEGORY_OF[t] is CATEGORY_OF[source] for t in targets)


def test_can_convert():
    assert can_convert(Format.WAV, Format.MP3)
    assert can_convert(Format.MOV, Format.GIF)
    assert not can_convert(Format.WAV, Format.WAV)
    assert not can_convert(Format.MP4, Format.MP3)  # different category
    assert not can_convert(Format.PNG, Format.GIF)


def test_eighteen_conversion_pairs():
    assert sum(len(allowed_targets(fmt)) for fmt in Format) == 18
    assert {CATEGORY_OF[fmt] for fmt in Format} == set(Category)


def test_formats_endpoint_matches_contract(auth_client):
    response = auth_client.get("/api/formats")
    assert response.status_code == 200
    assert response.json() == CONTRACT_FORMATS_RESPONSE


def test_formats_endpoint_uses_configured_limits(auth_client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_file_size", 1024)
    body = auth_client.get("/api/formats").json()
    assert body["max_file_size"] == 1024


def test_formats_endpoint_requires_login(client):
    response = client.get("/api/formats")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
