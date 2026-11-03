from pathlib import Path

import pytest

from app.conversion import storage
from app.conversion.formats import Format
from app.core.config import settings

JOB = "7f3a9c2e-4b1d-4e8a-9c3f-2a1b5d6e7f80"


def test_paths_are_built_from_ids_only():
    assert storage.upload_path(JOB, "file-1", Format.WAV) == (
        settings.data_dir / "uploads" / JOB / "file-1.wav"
    )
    assert storage.output_path(JOB, 1, Format.MP3) == settings.data_dir / "outputs" / JOB / "1.mp3"


def test_relative_paths_round_trip():
    path = storage.output_path(JOB, 0, Format.JPG)
    relative = storage.to_relative(path)
    assert relative == f"outputs/{JOB}/0.jpg"
    assert storage.to_absolute(relative) == path


@pytest.mark.parametrize("bad", ["", "../etc/passwd", "outputs/../../x", "/etc/passwd"])
def test_to_absolute_refuses_escaping_paths(bad):
    with pytest.raises(ValueError):
        storage.to_absolute(bad)


def test_remove_job_dirs():
    for path in (
        storage.upload_path(JOB, "a", Format.PNG),
        storage.output_path(JOB, 0, Format.JPG),
    ):
        path.parent.mkdir(parents=True)
        path.write_bytes(b"x")

    storage.remove_uploads(JOB)
    storage.remove_outputs(JOB)
    storage.remove_outputs(JOB)  # idempotent

    assert not storage.upload_dir(JOB).exists()
    assert not storage.output_dir(JOB).exists()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("nagranie.wav", "nagranie.wav"),
        ("C:\\fakepath\\zdjęcie.png", "zdjęcie.png"),
        ("../../etc/passwd.mp3", "passwd.mp3"),
        ("  film.mov  ", "film.mov"),
        ("photo.png.", "photo.png"),
        (".png", "plik.png"),
        ("", "plik"),
        ("...", "plik"),
        ("tab\there\x00.jpg", "tabhere.jpg"),
        ("evil\u202egnp.exe.png", "evilgnp.exe.png"),  # right-to-left override removed
        ("Ze\u0301bra.png", "Zébra.png"),  # NFC: e + combining acute -> é
    ],
)
def test_display_name(raw, expected):
    assert storage.display_name(raw) == expected


def test_display_name_shortens_keeping_extension():
    name = storage.display_name("a" * 300 + ".heic")
    assert len(name) == storage.MAX_NAME_LENGTH
    assert name.endswith("a.heic")


def test_display_name_long_suffix_is_not_an_extension():
    name = storage.display_name("x." + "b" * 300)
    assert len(name) == storage.MAX_NAME_LENGTH
    assert name.startswith("x.bbb")


@pytest.mark.parametrize(
    ("inputs", "target", "expected"),
    [
        (["nagranie.wav", "muzyka.flac"], Format.MP3, ["nagranie.mp3", "muzyka.mp3"]),
        (["foto.png", "foto.heic"], Format.JPG, ["foto.jpg", "foto (2).jpg"]),
        (["Foto.png", "foto.heic"], Format.JPG, ["Foto.jpg", "foto (2).jpg"]),  # case-insensitive
        (["film.mp4", "film.mp4"], Format.GIF, ["film.gif", "film (2).gif"]),
        (["my.holiday.mov"], Format.MP4, ["my.holiday.mp4"]),
        ([".png"], Format.JPG, ["plik.jpg"]),
        (["bez_rozszerzenia"], Format.PNG, ["bez_rozszerzenia.png"]),
    ],
)
def test_output_names(inputs, target, expected):
    assert storage.output_names(inputs, target) == expected


def test_data_dir_is_test_tmp():
    """Guard: the autouse fixture must redirect DATA_DIR away from ./data."""
    assert settings.data_dir != Path("./data")
