"""Audio converter: flac / mp3 / wav via FFmpeg, parameters from `presets.audio_args`."""

from pathlib import Path

from app.conversion import probe as media_probe  # module import: probe imports this package
from app.conversion.converters import presets
from app.conversion.converters.ffmpeg import run_ffmpeg
from app.conversion.formats import Format


def convert_audio(src: Path, dst: Path, source: Format, target: Format, timeout: int) -> None:
    info = media_probe.probe(src, source)
    if info.audio is None:  # probe() already guarantees this for audio formats
        raise ValueError("no audio stream")
    run_ffmpeg(src, source, presets.audio_args(info.audio, target), dst, target, timeout)
