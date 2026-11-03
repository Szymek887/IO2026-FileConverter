import subprocess

import pytest

from app.conversion.converters import ffmpeg
from app.conversion.converters.ffmpeg import (
    DEMUXERS,
    MUXERS,
    FFmpegError,
    ffmpeg_threads,
    run_ffmpeg,
    run_ffprobe,
)
from app.conversion.formats import CATEGORY_OF, Category, Format
from app.core.config import settings
from tests.conversion.conftest import requires_ffmpeg

AV_FORMATS = {fmt for fmt in Format if CATEGORY_OF[fmt] is not Category.IMAGE}


def test_every_audio_video_format_has_demuxer_and_muxer():
    assert set(DEMUXERS) == AV_FORMATS
    assert set(MUXERS) == AV_FORMATS


@pytest.mark.parametrize(("cpus", "workers", "expected"), [(8, 2, 4), (2, 2, 1), (1, 4, 1)])
def test_ffmpeg_threads(monkeypatch, cpus, workers, expected):
    monkeypatch.setattr(ffmpeg.os, "cpu_count", lambda: cpus)
    monkeypatch.setattr(settings, "worker_count", workers)
    assert ffmpeg_threads() == expected


@requires_ffmpeg
def test_writes_output_without_extension(media, tmp_path):
    """Outputs go to `*.part` files, so the muxer must not depend on the extension."""
    dst = tmp_path / "out.flac.part"
    run_ffmpeg(media / "stereo16.wav", Format.WAV, ["-c:a", "flac"], dst, Format.FLAC, 60)
    assert run_ffprobe(dst, Format.FLAC, 30)["format"]["format_name"] == "flac"


@requires_ffmpeg
def test_unicode_and_spaces_in_paths(media, tmp_path):
    src = tmp_path / "zażółć gęślą.wav"
    src.write_bytes((media / "stereo16.wav").read_bytes())
    data = run_ffprobe(src, Format.WAV, 30)
    assert data["streams"][0]["codec_type"] == "audio"


@requires_ffmpeg
def test_failure_raises_with_stderr(media, tmp_path):
    with pytest.raises(FFmpegError, match="exited with") as exc_info:
        run_ffmpeg(media / "notes.txt", Format.WAV, [], tmp_path / "x", Format.FLAC, 60)
    assert not exc_info.value.timeout


def test_timeout(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(ffmpeg.subprocess, "run", fake_run)
    with pytest.raises(FFmpegError, match="timed out") as exc_info:
        run_ffmpeg(tmp_path / "a.wav", Format.WAV, [], tmp_path / "b", Format.MP3, 5)
    assert exc_info.value.timeout


def test_missing_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ffprobe_path", str(tmp_path / "no-such-ffprobe"))
    with pytest.raises(FFmpegError, match="cannot run"):
        run_ffprobe(tmp_path / "a.wav", Format.WAV, 5)


def test_command_is_hardened(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(ffmpeg.subprocess, "run", fake_run)
    src, dst = tmp_path / "in.mp4", tmp_path / "out.part"
    run_ffmpeg(src, Format.MP4, ["-c", "copy"], dst, Format.MOV, 7)

    cmd, kwargs = calls[0]
    assert cmd[0] == settings.ffmpeg_path
    assert "-nostdin" in cmd
    i = cmd.index("-i")
    assert cmd[i - 4 : i + 2] == ["-protocol_whitelist", "file", "-f", "mov", "-i", str(src)]
    assert cmd[-3:] == ["-f", "mov", str(dst)]
    assert kwargs["timeout"] == 7
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert "shell" not in kwargs
