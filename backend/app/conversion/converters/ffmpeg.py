"""The only place that starts FFmpeg / ffprobe processes.

Every call is hardened against untrusted input files:
- the input demuxer is forced from the file's format (`-f mov`, ...), so FFmpeg never
  auto-detects playlists or other formats that could open URLs or other local files;
- `-protocol_whitelist file` – inputs may only be read from disk;
- list-form arguments (no shell), no stdin, a timeout that kills the process.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from app.conversion.formats import Format
from app.core.config import settings

# Format -> FFmpeg demuxer used to read it (mp4 and mov share the ISO-BMFF demuxer).
DEMUXERS: dict[Format, str] = {
    Format.FLAC: "flac",
    Format.MP3: "mp3",
    Format.WAV: "wav",
    Format.GIF: "gif",
    Format.MP4: "mov",
    Format.MOV: "mov",
}

# Format -> FFmpeg muxer used to write it (outputs are written to `*.part` files, so the
# muxer can't be guessed from the extension).
MUXERS: dict[Format, str] = {
    Format.FLAC: "flac",
    Format.MP3: "mp3",
    Format.WAV: "wav",
    Format.GIF: "gif",
    Format.MP4: "mp4",
    Format.MOV: "mov",
}

STDERR_TAIL_LINES = 5


class FFmpegError(Exception):
    """FFmpeg/ffprobe failed, timed out or is missing. The message is for logs only."""

    def __init__(self, message: str, *, timeout: bool = False) -> None:
        super().__init__(message)
        self.timeout = timeout


def ffmpeg_threads() -> int:
    """Threads per FFmpeg process, so `WORKER_COUNT` parallel jobs share the CPUs."""
    return max(1, (os.cpu_count() or 1) // settings.worker_count)


def _run(cmd: list[str], timeout: int) -> str:
    try:
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:  # the child is killed by subprocess.run
        raise FFmpegError(f"{Path(cmd[0]).name} timed out after {timeout} s", timeout=True) from exc
    except OSError as exc:  # binary missing / not executable
        raise FFmpegError(f"cannot run {cmd[0]}: {exc}") from exc

    if proc.returncode != 0:
        tail = " | ".join(proc.stderr.strip().splitlines()[-STDERR_TAIL_LINES:])
        raise FFmpegError(f"{Path(cmd[0]).name} exited with {proc.returncode}: {tail}")
    return proc.stdout


def _input_options(src_format: Format) -> list[str]:
    """Options that must precede the input file: local files only, forced demuxer."""
    return ["-protocol_whitelist", "file", "-f", DEMUXERS[src_format]]


def run_ffmpeg(
    src: Path,
    src_format: Format,
    output_args: list[str],
    dst: Path,
    dst_format: Format,
    timeout: int,
) -> None:
    """Run `ffmpeg <hardening> -f <demuxer> -i src <output_args> -f <muxer> dst`."""
    cmd = [
        settings.ffmpeg_path,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        *_input_options(src_format),
        "-i",
        str(src),
        *output_args,
        "-threads",
        str(ffmpeg_threads()),
        "-f",
        MUXERS[dst_format],
        str(dst),
    ]
    _run(cmd, timeout)


def run_ffprobe(src: Path, src_format: Format, timeout: int) -> dict[str, Any]:
    """`ffprobe -show_format -show_streams` as parsed JSON."""
    cmd = [
        settings.ffprobe_path,
        "-v",
        "error",
        *_input_options(src_format),
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(src),
    ]
    try:
        return json.loads(_run(cmd, timeout))
    except json.JSONDecodeError as exc:
        raise FFmpegError(f"ffprobe returned invalid JSON: {exc}") from exc
