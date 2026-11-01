"""Fixtures for conversion tests.

`media` generates small real sample files once per test session (nothing binary is
committed). Tests that need FFmpeg are skipped with a clear reason when it is missing.
"""

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from app.conversion.worker import ManualRunner
from app.core.config import settings


@pytest.fixture
def app(app):
    """The shared app, but jobs are only recorded (`app.state.job_runner.submitted`) –
    tests run `process_job()` themselves instead of racing worker threads."""
    app.state.job_runner = ManualRunner()
    return app


requires_ffmpeg = pytest.mark.skipif(
    not (shutil.which(settings.ffmpeg_path) and shutil.which(settings.ffprobe_path)),
    reason="FFmpeg/ffprobe not found on PATH",
)


def _ffmpeg(*args: str) -> None:
    subprocess.run(
        [settings.ffmpeg_path, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args],
        check=True,
        timeout=120,
    )


SINE = ["-f", "lavfi", "-i", "sine=frequency=440:duration=1"]
TESTSRC = ["-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=1"]


def _generate_av(d: Path) -> None:
    _ffmpeg(*SINE, "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(d / "stereo16.wav"))
    _ffmpeg(*SINE, "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", str(d / "mono24.wav"))
    _ffmpeg("-i", str(d / "mono24.wav"), "-c:a", "flac", "-sample_fmt", "s32",
            "-bits_per_raw_sample", "24", str(d / "mono24.flac"))  # fmt: skip
    _ffmpeg("-i", str(d / "stereo16.wav"), "-c:a", "libmp3lame", "-q:a", "0", str(d / "song.mp3"))
    _ffmpeg(*TESTSRC, *SINE, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", str(d / "clip.mp4"))  # fmt: skip
    _ffmpeg(*TESTSRC, *SINE, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le",
            "-shortest", str(d / "clip_pcm.mov"))  # fmt: skip
    _ffmpeg(*TESTSRC, "-vf", "fps=10", str(d / "anim.gif"))
    _ffmpeg(*SINE, "-c:a", "aac", str(d / "audio_only.mp4"))


def _generate_images(d: Path) -> None:
    Image.new("RGBA", (40, 30), (255, 0, 0, 128)).save(d / "alpha.png")
    Image.new("RGB", (40, 30), "blue").save(d / "photo.jpg", quality=95)
    Image.new("RGB", (40, 30), "green").save(d / "photo.heic", quality=90)
    jpg = (d / "photo.jpg").read_bytes()
    (d / "truncated.jpg").write_bytes(jpg[: len(jpg) // 2])


@pytest.fixture(scope="session")
def media(tmp_path_factory) -> Path:
    """Directory with sample files; audio/video samples exist only if FFmpeg is installed."""
    import pillow_heif

    pillow_heif.register_heif_opener()
    d = tmp_path_factory.mktemp("media")
    _generate_images(d)
    (d / "notes.txt").write_text("not a media file " * 100, encoding="utf-8")
    (d / "empty.bin").write_bytes(b"")
    if shutil.which(settings.ffmpeg_path):
        _generate_av(d)
    return d
