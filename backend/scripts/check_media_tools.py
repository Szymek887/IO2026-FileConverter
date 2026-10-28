"""Check that FFmpeg, Pillow and pillow-heif can do every kind of work the converter needs.

Runs tiny real conversions (audio, video, GIF palette, HEIC encode/decode) in a temp
directory and prints a report. Exit code 1 if anything is missing.

    uv run python scripts/check_media_tools.py
"""

import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

REQUIRED_ENCODERS = ["libmp3lame", "libx264", "aac", "flac", "pcm_s16le", "pcm_s24le", "gif"]
REQUIRED_DECODERS = ["mp3", "flac", "h264", "hevc", "prores", "gif", "aac"]
REQUIRED_DEMUXERS = ["mov", "mp3", "flac", "wav", "gif"]
REQUIRED_FILTERS = ["palettegen", "paletteuse", "scale", "fps", "split"]

results: list[tuple[str, bool, str]] = []


def check(name: str) -> Callable[[Callable[[], str]], Callable[[], str]]:
    def decorator(fn: Callable[[], str]) -> Callable[[], str]:
        try:
            results.append((name, True, fn()))
        except Exception as exc:
            results.append((name, False, f"{type(exc).__name__}: {exc}"))
        return fn

    return decorator


def run(*args: str) -> str:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip().splitlines()[-1] if proc.stderr else "failed")
    return proc.stdout


def ffmpeg(*args: str) -> None:
    run(FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args)


def probe_format(path: Path, demuxer: str) -> str:
    out = run(
        FFPROBE,
        "-v",
        "error",
        "-f",
        demuxer,
        "-show_entries",
        "format=format_name:stream=codec_name",
        "-of",
        "compact=p=0:nk=1",
        str(path),
    )
    return " ".join(out.split())


def listed(kind: str) -> set[str]:
    """Names from `ffmpeg -<kind>`: 2nd column, which may be comma-joined (`mov,mp4,...`)."""
    names: set[str] = set()
    for line in run(FFMPEG, "-hide_banner", f"-{kind}").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            names.update(parts[1].split(","))
    return names


def require_listed(kind: str, names: list[str]) -> str:
    available = listed(kind)
    missing = [n for n in names if n not in available]
    if missing:
        raise RuntimeError(f"missing {kind}: {', '.join(missing)}")
    return ", ".join(names)


tmp = Path(tempfile.mkdtemp(prefix="media-check-"))


@check("ffmpeg / ffprobe on PATH")
def _binaries() -> str:
    for binary in (FFMPEG, FFPROBE):
        if shutil.which(binary) is None:
            raise RuntimeError(f"{binary} not found")
    return run(FFMPEG, "-version").splitlines()[0]


@check("ffmpeg encoders")
def _encoders() -> str:
    return require_listed("encoders", REQUIRED_ENCODERS)


@check("ffmpeg decoders")
def _decoders() -> str:
    return require_listed("decoders", REQUIRED_DECODERS)


@check("ffmpeg demuxers")
def _demuxers() -> str:
    return require_listed("demuxers", REQUIRED_DEMUXERS)


@check("ffmpeg filters")
def _filters() -> str:
    return require_listed("filters", REQUIRED_FILTERS)


@check("audio: wav 24-bit -> flac / mp3 / wav 16-bit")
def _audio() -> str:
    wav = tmp / "in.wav"
    sine = ["-f", "lavfi", "-i", "sine=frequency=440:duration=1:sample_rate=48000"]
    ffmpeg(*sine, "-ac", "2", "-c:a", "pcm_s24le", str(wav))
    ffmpeg(
        "-f",
        "wav",
        "-i",
        str(wav),
        "-c:a",
        "flac",
        "-sample_fmt",
        "s32",
        "-bits_per_raw_sample",
        "24",
        "-compression_level",
        "8",
        str(tmp / "out.flac"),
    )
    ffmpeg("-f", "wav", "-i", str(wav), "-c:a", "libmp3lame", "-q:a", "0", str(tmp / "out.mp3"))
    ffmpeg("-f", "flac", "-i", str(tmp / "out.flac"), "-c:a", "pcm_s16le", str(tmp / "out.wav"))
    return " | ".join(
        probe_format(tmp / name, fmt)
        for name, fmt in [("out.flac", "flac"), ("out.mp3", "mp3"), ("out.wav", "wav")]
    )


@check("video: h264 mp4 -> mov remux, -> gif (palette), gif -> mp4")
def _video() -> str:
    mp4 = tmp / "in.mp4"
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=320x240:rate=25:duration=2",
        "-f",
        "lavfi",
        "-i",
        "sine=duration=2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(mp4),
    )
    ffmpeg(
        "-f",
        "mov",
        "-i",
        str(mp4),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c",
        "copy",
        str(tmp / "out.mov"),
    )
    palette = (
        "fps=15,scale=640:-1:flags=lanczos,split[a][b];"
        "[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a"
    )
    ffmpeg(
        "-f", "mov", "-i", str(mp4), "-filter_complex", palette, "-loop", "0", str(tmp / "out.gif")
    )
    ffmpeg(
        "-f",
        "gif",
        "-i",
        str(tmp / "out.gif"),
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "slow",
        "-pix_fmt",
        "yuv420p",
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-movflags",
        "+faststart",
        "-an",
        str(tmp / "out.mp4"),
    )
    return " | ".join(
        probe_format(tmp / name, fmt)
        for name, fmt in [("out.mov", "mov"), ("out.gif", "gif"), ("out.mp4", "mov")]
    )


@check("images: png (RGBA) -> heic -> jpg / png")
def _images() -> str:
    import pillow_heif
    from PIL import Image

    pillow_heif.register_heif_opener()
    src = Image.new("RGBA", (64, 48), (200, 30, 30, 128))
    src.save(tmp / "in.png")

    with Image.open(tmp / "in.png", formats=["PNG"]) as img:
        img.save(tmp / "out.heic", quality=90)
    with Image.open(tmp / "out.heic", formats=["HEIF"]) as img:
        img.verify()
    with Image.open(tmp / "out.heic", formats=["HEIF"]) as img:
        heic_info = f"HEIF {img.size} {img.mode}"
        flat = Image.new("RGB", img.size, "white")
        flat.paste(img, mask=img.getchannel("A") if img.mode == "RGBA" else None)
        flat.save(tmp / "out.jpg", quality=95, subsampling=0)
        img.save(tmp / "out.png")
    with Image.open(tmp / "out.jpg", formats=["JPEG"]) as jpg:
        jpg_info = f"JPEG {jpg.size} {jpg.mode}"

    info = pillow_heif.libheif_info()
    encoders = ", ".join(info.get("encoders", {})) or "none"
    return f"libheif {info['libheif']} (encoders: {encoders}) | {heic_info} | {jpg_info}"


def main() -> int:
    shutil.rmtree(tmp, ignore_errors=True)
    width = max(len(name) for name, _, _ in results)
    for name, ok, detail in results:
        print(f"[{'OK' if ok else 'FAIL'}] {name.ljust(width)}  {detail}")
    print(f"python {sys.version.split()[0]} on {sys.platform}")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
