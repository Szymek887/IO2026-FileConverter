"""Conversion matrix: every allowed source -> target pair, converted for real.

One or more samples per source format (generated at test time, nothing binary committed);
each output must probe as the target format and keep what the user expects – duration
(audio/video), frame size (video), image size after EXIF orientation, no alpha in JPG.
The per-category test files cover the details; this file proves the matrix is complete.
"""

from dataclasses import dataclass
from pathlib import Path

import pytest
from PIL import Image, ImageCms

from app.conversion.converters import convert
from app.conversion.formats import CATEGORY_OF, Category, Format, allowed_targets
from app.conversion.probe import probe
from app.core.config import settings
from tests.conversion.conftest import SINE, TESTSRC, _ffmpeg, requires_ffmpeg
from tests.conversion.test_audio import pcm_md5

DURATION_TOLERANCE = 0.2  # seconds


@dataclass(frozen=True)
class Sample:
    name: str
    format: Format
    duration: float | None = None  # audio/video
    size: tuple[int, int] | None = None  # video frame / image after orientation


SAMPLES = [
    Sample("stereo16.wav", Format.WAV, duration=1.0),
    Sample("mono24.flac", Format.FLAC, duration=1.0),
    Sample("song.mp3", Format.MP3, duration=1.0),
    Sample("clip.mp4", Format.MP4, duration=1.0, size=(320, 240)),  # h264 + aac
    Sample("clip_pcm.mov", Format.MOV, duration=1.0, size=(320, 240)),  # h264 + pcm: remux
    Sample("prores.mov", Format.MOV, duration=1.0, size=(320, 240)),  # prores: transcode
    Sample("anim2s.gif", Format.GIF, duration=2.0, size=(320, 240)),
    Sample("alpha.png", Format.PNG, size=(40, 30)),  # RGBA
    Sample("oriented.jpg", Format.JPG, size=(30, 40)),  # stored 40x30, EXIF orientation 6
    Sample("photo.heic", Format.HEIC, size=(40, 30)),
]

CASES = [(sample, target) for sample in SAMPLES for target in allowed_targets(sample.format)]

# Codec of the output stream per target (mp4/mov: every source here ends up as H.264).
TARGET_CODECS = {
    Format.FLAC: ("flac",),
    Format.MP3: ("mp3",),
    Format.WAV: ("pcm_s16le", "pcm_s24le"),
    Format.MP4: ("h264",),
    Format.MOV: ("h264",),
    Format.GIF: ("gif",),
}


@pytest.fixture(scope="module")
def samples(media, tmp_path_factory) -> Path:
    """`media` plus the matrix-only samples."""
    d = tmp_path_factory.mktemp("matrix")
    for sample in SAMPLES:
        if (media / sample.name).exists():
            (d / sample.name).write_bytes((media / sample.name).read_bytes())

    _ffmpeg(*TESTSRC, *SINE, "-c:v", "prores_ks", "-profile:v", "1", "-c:a", "pcm_s16le",
            "-shortest", str(d / "prores.mov"))  # fmt: skip
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x240:rate=10:duration=2",
            str(d / "anim2s.gif"))  # fmt: skip

    img = Image.new("RGB", (40, 30), "blue")
    img.paste((255, 0, 0), (0, 0, 20, 30))
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation: rotate 90° clockwise
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    img.save(d / "oriented.jpg", quality=95, exif=exif.tobytes(), icc_profile=srgb)
    return d


def test_matrix_covers_all_18_pairs():
    pairs = {(sample.format, target) for sample, target in CASES}
    expected = {(source, target) for source in Format for target in allowed_targets(source)}
    assert pairs == expected
    assert len(expected) == 18


@requires_ffmpeg
@pytest.mark.parametrize(
    ("sample", "target"),
    CASES,
    ids=[f"{sample.name}-{target}" for sample, target in CASES],
)
def test_conversion(samples, tmp_path, sample: Sample, target: Format):
    dst = tmp_path / f"out.{target}"
    convert(samples / sample.name, dst, sample.format, target, settings.conversion_timeout_seconds)
    info = probe(dst, target)  # raises if the output isn't a valid `target` file
    assert info.format is target

    if CATEGORY_OF[target] is Category.IMAGE:
        assert (info.image.width, info.image.height) == sample.size
        if target is Format.JPG:
            assert not info.image.has_alpha
        return

    assert info.duration == pytest.approx(sample.duration, abs=DURATION_TOLERANCE)
    if CATEGORY_OF[target] is Category.AUDIO:
        assert info.audio.codec in TARGET_CODECS[target]
    else:
        assert info.video.codec in TARGET_CODECS[target]
        assert (info.video.width, info.video.height) == sample.size


@requires_ffmpeg
@pytest.mark.parametrize(
    ("name", "source", "target", "codec"),
    [
        ("stereo16.wav", Format.WAV, Format.FLAC, "pcm_s16le"),
        ("mono24.flac", Format.FLAC, Format.WAV, "pcm_s24le"),
    ],
)
def test_lossless_audio_is_bit_exact(samples, tmp_path, name, source, target, codec):
    dst = tmp_path / f"out.{target}"
    convert(samples / name, dst, source, target, settings.conversion_timeout_seconds)
    assert pcm_md5(dst, target, codec) == pcm_md5(samples / name, source, codec)
