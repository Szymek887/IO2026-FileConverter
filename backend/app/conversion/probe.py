"""Inspect an uploaded file: does its content really match its extension, and what is in it?

`probe()` is used twice: by upload validation (failure -> `422 CORRUPTED_FILE`) and by the
worker right before converting (the presets depend on bit depth, frame rate, alpha, ...).
Audio/video are checked with ffprobe using the demuxer of the claimed format, images with
Pillow restricted to the claimed format.
"""

import warnings
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import pillow_heif
from PIL import Image

from app.conversion.converters.ffmpeg import FFmpegError, run_ffprobe
from app.conversion.formats import CATEGORY_OF, Category, Format
from app.core.config import settings

pillow_heif.register_heif_opener()

# Format -> Pillow plugin name allowed to open it.
PILLOW_FORMATS: dict[Format, str] = {Format.JPG: "JPEG", Format.PNG: "PNG", Format.HEIC: "HEIF"}


class ProbeError(Exception):
    """The file is unreadable or its content doesn't match the format. Message is for logs."""


@dataclass(frozen=True)
class AudioStream:
    codec: str
    sample_rate: int
    channels: int
    bit_depth: int | None  # None for lossy codecs (mp3)


@dataclass(frozen=True)
class VideoStream:
    codec: str
    width: int
    height: int
    fps: float | None


@dataclass(frozen=True)
class ImageInfo:
    width: int
    height: int
    mode: str
    has_alpha: bool


@dataclass(frozen=True)
class MediaInfo:
    format: Format
    duration: float | None = None  # seconds; audio/video only
    audio: AudioStream | None = None  # first audio stream
    video: VideoStream | None = None  # first real video stream (cover art excluded)
    image: ImageInfo | None = None
    audio_codecs: tuple[str, ...] = ()  # of all audio tracks


def probe(path: Path, fmt: Format) -> MediaInfo:
    """Check that `path` is a valid `fmt` file and describe it; raise `ProbeError` if not."""
    if not path.is_file() or path.stat().st_size == 0:
        raise ProbeError("file is empty")
    if CATEGORY_OF[fmt] is Category.IMAGE:
        return _probe_image(path, fmt)
    return _probe_av(path, fmt)


def _probe_av(path: Path, fmt: Format) -> MediaInfo:
    try:
        data = run_ffprobe(path, fmt, settings.probe_timeout_seconds)
    except FFmpegError as exc:
        raise ProbeError(str(exc)) from exc

    streams = data.get("streams", [])
    audio_streams = [_audio_stream(s) for s in streams if s.get("codec_type") == "audio"]
    audio = audio_streams[0] if audio_streams else None
    video = next(
        (
            _video_stream(s)
            for s in streams
            if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
        ),
        None,
    )
    duration = _float(data.get("format", {}).get("duration"))

    if CATEGORY_OF[fmt] is Category.AUDIO:
        if audio is None:
            raise ProbeError("no audio stream")
        if not duration:
            raise ProbeError("audio has no duration")
    elif video is None:
        raise ProbeError("no video stream")
    return MediaInfo(
        format=fmt,
        duration=duration,
        audio=audio,
        video=video,
        audio_codecs=tuple(stream.codec for stream in audio_streams),
    )


def _audio_stream(stream: dict[str, Any]) -> AudioStream:
    bit_depth = _int(stream.get("bits_per_raw_sample")) or _int(stream.get("bits_per_sample"))
    return AudioStream(
        codec=stream.get("codec_name", ""),
        sample_rate=_int(stream.get("sample_rate")),
        channels=_int(stream.get("channels")),
        bit_depth=bit_depth or None,
    )


def _video_stream(stream: dict[str, Any]) -> VideoStream:
    rate = _fraction(stream.get("avg_frame_rate")) or _fraction(stream.get("r_frame_rate"))
    return VideoStream(
        codec=stream.get("codec_name", ""),
        width=_int(stream.get("width")),
        height=_int(stream.get("height")),
        fps=float(rate) if rate else None,
    )


def _probe_image(path: Path, fmt: Format) -> MediaInfo:
    Image.MAX_IMAGE_PIXELS = settings.max_image_pixels  # Pillow refuses 2x this outright
    allowed = [PILLOW_FORMATS[fmt]]
    try:
        with warnings.catch_warnings():
            # Above MAX_IMAGE_PIXELS Pillow only warns – make it an error instead.
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(path, formats=allowed)
        with img:
            if img.width * img.height > settings.max_image_pixels:
                raise ProbeError(f"image too large: {img.width}x{img.height}")
            img.verify()
        # verify() leaves the image unusable and skips pixel data in some formats –
        # reopen and decode fully to catch truncated files.
        with Image.open(path, formats=allowed) as img:
            img.load()
            info = ImageInfo(
                width=img.width,
                height=img.height,
                mode=img.mode,
                has_alpha=img.mode in ("RGBA", "LA", "PA")
                or (img.mode == "P" and "transparency" in img.info),
            )
    except ProbeError:
        raise
    except Exception as exc:  # UnidentifiedImageError, DecompressionBombError, OSError, ...
        raise ProbeError(f"{type(exc).__name__}: {exc}") from exc
    return MediaInfo(format=fmt, image=info)


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fraction(value: Any) -> Fraction | None:
    try:
        rate = Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        return None
    return rate or None
