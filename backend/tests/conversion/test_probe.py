import pytest

from app.conversion.formats import Format
from app.conversion.probe import ProbeError, probe
from app.core.config import settings
from tests.conversion.conftest import requires_ffmpeg

# --- audio / video ---------------------------------------------------------------------


@requires_ffmpeg
def test_wav_16_bit_stereo(media):
    info = probe(media / "stereo16.wav", Format.WAV)
    assert info.audio is not None
    assert (info.audio.codec, info.audio.sample_rate, info.audio.channels) == (
        "pcm_s16le",
        44100,
        2,
    )
    assert info.audio.bit_depth == 16
    assert info.duration == pytest.approx(1.0, abs=0.05)
    assert info.video is None


@requires_ffmpeg
@pytest.mark.parametrize(
    ("name", "fmt"), [("mono24.wav", Format.WAV), ("mono24.flac", Format.FLAC)]
)
def test_24_bit_audio(media, name, fmt):
    info = probe(media / name, fmt)
    assert info.audio.bit_depth == 24
    assert (info.audio.sample_rate, info.audio.channels) == (48000, 1)


@requires_ffmpeg
def test_mp3_has_no_bit_depth(media):
    info = probe(media / "song.mp3", Format.MP3)
    assert info.audio.codec == "mp3"
    assert info.audio.bit_depth is None


@requires_ffmpeg
@pytest.mark.parametrize("fmt", [Format.MP4, Format.MOV])  # mp4/mov share one demuxer
def test_mp4_video(media, fmt):
    info = probe(media / "clip.mp4", fmt)
    assert info.video.codec == "h264"
    assert (info.video.width, info.video.height) == (320, 240)
    assert info.video.fps == pytest.approx(25)
    assert info.audio.codec == "aac"


@requires_ffmpeg
def test_mov_with_pcm_audio(media):
    info = probe(media / "clip_pcm.mov", Format.MOV)
    assert info.audio.codec == "pcm_s16le"


@requires_ffmpeg
def test_gif(media):
    info = probe(media / "anim.gif", Format.GIF)
    assert info.video.codec == "gif"
    assert info.video.fps == pytest.approx(10)
    assert info.audio is None


@requires_ffmpeg
@pytest.mark.parametrize(
    ("name", "fmt"),
    [
        ("notes.txt", Format.WAV),
        ("notes.txt", Format.MP3),
        ("notes.txt", Format.FLAC),
        ("notes.txt", Format.MP4),
        ("notes.txt", Format.GIF),
        ("stereo16.wav", Format.FLAC),  # real audio, wrong extension
        ("clip.mp4", Format.GIF),
        ("anim.gif", Format.MP4),
        ("audio_only.mp4", Format.MP4),  # no video stream
        ("clip.mp4", Format.WAV),
        ("empty.bin", Format.MP3),
    ],
)
def test_invalid_audio_video(media, name, fmt):
    with pytest.raises(ProbeError):
        probe(media / name, fmt)


# --- images (no FFmpeg needed) ---------------------------------------------------------


def test_png_with_alpha(media):
    info = probe(media / "alpha.png", Format.PNG)
    assert (info.image.width, info.image.height, info.image.mode) == (40, 30, "RGBA")
    assert info.image.has_alpha


@pytest.mark.parametrize(("name", "fmt"), [("photo.jpg", Format.JPG), ("photo.heic", Format.HEIC)])
def test_opaque_images(media, name, fmt):
    info = probe(media / name, fmt)
    assert (info.image.width, info.image.height) == (40, 30)
    assert not info.image.has_alpha


@pytest.mark.parametrize(
    ("name", "fmt"),
    [
        ("notes.txt", Format.PNG),
        ("alpha.png", Format.JPG),  # real image, wrong extension
        ("photo.jpg", Format.HEIC),
        ("photo.heic", Format.PNG),
        ("truncated.jpg", Format.JPG),
        ("empty.bin", Format.PNG),
    ],
)
def test_invalid_images(media, name, fmt):
    with pytest.raises(ProbeError):
        probe(media / name, fmt)


def test_too_many_pixels(media, monkeypatch):
    monkeypatch.setattr(settings, "max_image_pixels", 40 * 30 - 1)
    with pytest.raises(ProbeError, match="DecompressionBomb"):
        probe(media / "photo.jpg", Format.JPG)


def test_missing_file(tmp_path):
    with pytest.raises(ProbeError):
        probe(tmp_path / "missing.png", Format.PNG)
