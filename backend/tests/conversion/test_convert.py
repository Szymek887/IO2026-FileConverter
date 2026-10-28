"""The `convert()` contract, tested with fake category converters (real ones: B9–B12)."""

import pytest

from app.conversion import converters
from app.conversion.converters import ConversionError, FFmpegError, convert
from app.conversion.formats import Category, Format


@pytest.fixture
def fake_converters(monkeypatch):
    """Empty converter registry the test can fill: `fake_converters[Category.AUDIO] = fn`."""
    registry = {}
    monkeypatch.setattr(converters, "CONVERTERS", registry)
    return registry


@pytest.fixture
def src(tmp_path):
    path = tmp_path / "in.wav"
    path.write_bytes(b"input")
    return path


def test_success_renames_part_file(fake_converters, src, tmp_path):
    calls = []

    def fake(src_path, dst_path, source, target, timeout):
        calls.append((src_path, dst_path, source, target, timeout))
        dst_path.write_bytes(b"output")

    fake_converters[Category.AUDIO] = fake
    dst = tmp_path / "out" / "0.mp3"
    convert(src, dst, Format.WAV, Format.MP3, 30)

    assert dst.read_bytes() == b"output"
    assert calls == [(src, dst.with_name("0.mp3.part"), Format.WAV, Format.MP3, 30)]
    assert not dst.with_name("0.mp3.part").exists()


@pytest.mark.parametrize(("source", "target"), [(Format.WAV, Format.WAV), (Format.WAV, Format.PNG)])
def test_disallowed_pair(fake_converters, src, tmp_path, source, target):
    fake_converters[Category.AUDIO] = lambda *args: pytest.fail("converter must not run")
    with pytest.raises(ConversionError, match="not allowed"):
        convert(src, tmp_path / "out", source, target, 30)


def test_category_without_converter(fake_converters, src, tmp_path):
    with pytest.raises(ConversionError, match="no converter"):
        convert(src, tmp_path / "out.mp3", Format.WAV, Format.MP3, 30)


def test_ffmpeg_timeout_is_reported(fake_converters, src, tmp_path):
    def fake(src_path, dst_path, *args):
        dst_path.write_bytes(b"half")
        raise FFmpegError("ffmpeg timed out", timeout=True)

    fake_converters[Category.AUDIO] = fake
    dst = tmp_path / "out.mp3"
    with pytest.raises(ConversionError) as exc_info:
        convert(src, dst, Format.WAV, Format.MP3, 30)

    assert exc_info.value.timeout
    assert not dst.exists()
    assert not dst.with_name("out.mp3.part").exists()


def test_unexpected_exception_is_wrapped(fake_converters, src, tmp_path):
    def fake(*args):
        raise OSError("cannot identify image file")

    fake_converters[Category.IMAGE] = fake
    with pytest.raises(ConversionError, match="OSError") as exc_info:
        convert(src, tmp_path / "out.jpg", Format.PNG, Format.JPG, 30)
    assert not exc_info.value.timeout


@pytest.mark.parametrize("output", [None, b""])
def test_missing_or_empty_output(fake_converters, src, tmp_path, output):
    def fake(src_path, dst_path, *args):
        if output is not None:
            dst_path.write_bytes(output)

    fake_converters[Category.VIDEO] = fake
    dst = tmp_path / "out.gif"
    with pytest.raises(ConversionError, match="no output"):
        convert(src, dst, Format.MP4, Format.GIF, 30)
    assert not dst.exists()
    assert not dst.with_name("out.gif.part").exists()
