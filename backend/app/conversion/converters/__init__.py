"""Conversion engine: one entry point, `convert()`, dispatching to a converter per category.

Converters write to a temporary `*.part` file; `convert()` renames it to `dst` only when it
is non-empty, so a partially written output is never served. All parameters are chosen
automatically (presets), the user only picks the target format.
"""

import logging
from collections.abc import Callable
from pathlib import Path

from app.conversion.converters.ffmpeg import FFmpegError
from app.conversion.formats import CATEGORY_OF, Category, Format, can_convert

logger = logging.getLogger(__name__)

# (src, dst, source format, target format, timeout in seconds) -> None; raises on failure.
Converter = Callable[[Path, Path, Format, Format, int], None]

CONVERTERS: dict[Category, Converter] = {}  # image (B10) and video (B12) follow


class ConversionError(Exception):
    """A file could not be converted. `reason` is for logs; users get a Polish message."""

    def __init__(self, reason: str, *, timeout: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.timeout = timeout


def convert(src: Path, dst: Path, source: Format, target: Format, timeout: int) -> None:
    """Convert `src` (in `source` format) to `dst` (in `target` format) or raise
    `ConversionError`. `timeout` limits a single external process (FFmpeg)."""
    if not can_convert(source, target):
        raise ConversionError(f"conversion {source} -> {target} is not allowed")
    converter = CONVERTERS.get(CATEGORY_OF[source])
    if converter is None:
        raise ConversionError(f"no converter for {CATEGORY_OF[source]} files")

    dst.parent.mkdir(parents=True, exist_ok=True)
    part = dst.with_name(dst.name + ".part")
    try:
        try:
            converter(src, part, source, target, timeout)
        except ConversionError:
            raise
        except FFmpegError as exc:
            raise ConversionError(str(exc), timeout=exc.timeout) from exc
        except Exception as exc:  # Pillow / pillow-heif errors, unexpected media
            raise ConversionError(f"{type(exc).__name__}: {exc}") from exc

        if not part.is_file() or part.stat().st_size == 0:
            raise ConversionError("converter produced no output")
        part.replace(dst)
    except ConversionError as exc:
        part.unlink(missing_ok=True)
        logger.warning("Conversion %s -> %s failed for %s: %s", source, target, src.name, exc)
        raise


# Registered at the bottom: the category modules import from this package.
from app.conversion.converters.audio import convert_audio  # noqa: E402

CONVERTERS[Category.AUDIO] = convert_audio

__all__ = ["CONVERTERS", "ConversionError", "Converter", "FFmpegError", "convert"]
