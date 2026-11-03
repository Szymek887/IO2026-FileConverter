"""Registry of supported formats: categories, allowed conversions, aliases and MIME types.

Single source of truth for validation, converters and `GET /api/formats`.
A conversion is allowed between two different formats of the same category.
"""

from enum import StrEnum


class Category(StrEnum):
    AUDIO = "audio"
    VIDEO = "video"
    IMAGE = "image"


class Format(StrEnum):
    FLAC = "flac"
    MP3 = "mp3"
    WAV = "wav"
    GIF = "gif"
    MP4 = "mp4"
    MOV = "mov"
    JPG = "jpg"
    PNG = "png"
    HEIC = "heic"


CATEGORY_FORMATS: dict[Category, tuple[Format, ...]] = {
    Category.AUDIO: (Format.FLAC, Format.MP3, Format.WAV),
    Category.VIDEO: (Format.GIF, Format.MP4, Format.MOV),
    Category.IMAGE: (Format.JPG, Format.PNG, Format.HEIC),
}

CATEGORY_OF: dict[Format, Category] = {
    fmt: category for category, formats in CATEGORY_FORMATS.items() for fmt in formats
}

CATEGORY_LABELS: dict[Category, str] = {
    Category.AUDIO: "Audio",
    Category.VIDEO: "Wideo",
    Category.IMAGE: "Obraz",
}

EXTENSION_ALIASES: dict[str, Format] = {"jpeg": Format.JPG, "heif": Format.HEIC}

MIME_TYPES: dict[Format, str] = {
    Format.FLAC: "audio/flac",
    Format.MP3: "audio/mpeg",
    Format.WAV: "audio/wav",
    Format.GIF: "image/gif",
    Format.MP4: "video/mp4",
    Format.MOV: "video/quicktime",
    Format.JPG: "image/jpeg",
    Format.PNG: "image/png",
    Format.HEIC: "image/heic",
}


def parse_format(value: str) -> Format | None:
    """`"MP3"` -> `Format.MP3`, `"jpeg"` -> `Format.JPG`; `None` if unsupported."""
    value = value.strip().lower()
    if value in EXTENSION_ALIASES:
        return EXTENSION_ALIASES[value]
    try:
        return Format(value)
    except ValueError:
        return None


def format_from_filename(filename: str) -> Format | None:
    """Format from the extension of an uploaded file name (case-insensitive, aliases applied).

    Only the last extension counts (`archive.tar.gz` -> `gz` -> `None`). Directory parts
    sent by some browsers (`C:\\fakepath\\photo.png`) are ignored.
    """
    basename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    _, dot, extension = basename.rpartition(".")
    return parse_format(extension) if dot else None


def allowed_targets(source: Format) -> list[Format]:
    """Other formats of the same category, in registry order."""
    return [fmt for fmt in CATEGORY_FORMATS[CATEGORY_OF[source]] if fmt != source]


def can_convert(source: Format, target: Format) -> bool:
    return target in allowed_targets(source)
