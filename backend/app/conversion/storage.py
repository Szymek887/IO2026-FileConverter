"""Where job files live on disk, and how user-supplied names are made safe to display.

    DATA_DIR/uploads/{job_id}/{file_id}.{ext}   inputs, deleted when the job finishes
    DATA_DIR/outputs/{job_id}/{index}.{ext}     outputs, deleted by retention

Paths on disk are built only from generated IDs; the user's file names are stored in the
database for display and download names. DB columns hold paths relative to `DATA_DIR`.
"""

import shutil
import unicodedata
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from app.conversion.formats import Format
from app.core.config import settings

MAX_NAME_LENGTH = 200
MAX_KEPT_EXTENSION_LENGTH = 10  # longer "extensions" are just part of a long name
DEFAULT_STEM = "plik"


def uploads_root() -> Path:
    return settings.data_dir / "uploads"


def outputs_root() -> Path:
    return settings.data_dir / "outputs"


def upload_dir(job_id: str) -> Path:
    return uploads_root() / job_id


def output_dir(job_id: str) -> Path:
    return outputs_root() / job_id


def upload_path(job_id: str, file_id: str, fmt: Format) -> Path:
    return upload_dir(job_id) / f"{file_id}.{fmt}"


def output_path(job_id: str, index: int, fmt: Format) -> Path:
    return output_dir(job_id) / f"{index}.{fmt}"


def to_relative(path: Path) -> str:
    """Path to store in the DB: relative to `DATA_DIR`, with `/` separators."""
    return path.relative_to(settings.data_dir).as_posix()


def to_absolute(relative: str) -> Path:
    """Inverse of `to_relative`. Refuses paths that would leave `DATA_DIR`."""
    parts = PurePosixPath(relative).parts
    if not parts or PurePosixPath(relative).is_absolute() or ".." in parts:
        raise ValueError(f"invalid stored path: {relative!r}")
    return settings.data_dir.joinpath(*parts)


def remove_uploads(job_id: str) -> None:
    shutil.rmtree(upload_dir(job_id), ignore_errors=True)


def remove_outputs(job_id: str) -> None:
    shutil.rmtree(output_dir(job_id), ignore_errors=True)


def display_name(raw: str) -> str:
    """Make an uploaded file name safe to store and show.

    Drops directory parts (`C:\\fakepath\\a.png` -> `a.png`), control and invisible
    formatting characters (e.g. right-to-left override used to fake extensions),
    normalizes to NFC and shortens to `MAX_NAME_LENGTH` keeping the extension.
    A name without a stem gets `plik` (`.png` -> `plik.png`).
    """
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    name = unicodedata.normalize("NFC", name)
    name = "".join(ch for ch in name if unicodedata.category(ch) not in ("Cc", "Cf"))
    name = name.strip().rstrip(".")  # trailing dots are dropped by Windows anyway

    stem, dot, extension = name.rpartition(".")
    if not dot or len(extension) > MAX_KEPT_EXTENSION_LENGTH:
        stem, dot, extension = name, "", ""
    stem = stem.strip() or DEFAULT_STEM
    return stem[: MAX_NAME_LENGTH - len(dot + extension)] + dot + extension


def content_disposition(name: str) -> str:
    """`Content-Disposition` of a download. Browsers use the UTF-8 `filename*`; `filename`
    is an ASCII fallback for clients that don't understand it."""
    decomposed = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    fallback = decomposed.replace('"', "").replace("\\", "")
    if fallback.startswith("."):  # nothing left of the stem (`日本語.jpg`)
        fallback = DEFAULT_STEM + fallback
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name, safe='')}"


def output_names(input_names: list[str], target: Format) -> list[str]:
    """Download names: input stem + target extension, unique within the job
    (case-insensitive, so both survive a download into one folder on Windows/macOS):
    `["foto.png", "foto.heic"]` -> `["foto.jpg", "foto (2).jpg"]`."""
    names: list[str] = []
    taken: set[str] = set()
    for input_name in input_names:
        name = display_name(input_name)
        stem = name.rpartition(".")[0] or name
        candidate, counter = f"{stem}.{target}", 1
        while candidate.lower() in taken:
            counter += 1
            candidate = f"{stem} ({counter}).{target}"
        taken.add(candidate.lower())
        names.append(candidate)
    return names
