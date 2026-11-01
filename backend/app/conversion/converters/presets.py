"""Every quality parameter of the conversion engine, in one place.

The user doesn't choose parameters – these functions pick them from what `probe()` found,
following the requirements: lossless where both formats allow it (FLAC, WAV), otherwise the
highest sensible quality (MP3). Tune quality here without touching the converter logic.
"""

from typing import TYPE_CHECKING

from app.conversion.formats import Format

if TYPE_CHECKING:  # probe.py imports this package, so no runtime import from it
    from app.conversion.probe import AudioStream

# --- audio -----------------------------------------------------------------------------

FLAC_COMPRESSION_LEVEL = "8"  # slowest/smallest; FLAC is lossless at every level
MP3_VBR_QUALITY = "0"  # LAME V0, highest-quality VBR
MP3_MAX_CHANNELS = 2
# Sample rates an MP3 (MPEG-1/2/2.5 Layer III) can store.
MP3_SAMPLE_RATES = (8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000)


def mp3_sample_rate(rate: int) -> int:
    """Closest MP3-compatible rate that loses nothing it doesn't have to: valid rates are
    kept, 88.2/176.4 kHz halve exactly to 44.1 kHz, other high rates go to 48 kHz and odd
    low rates up to the next valid one."""
    if rate in MP3_SAMPLE_RATES:
        return rate
    if rate > MP3_SAMPLE_RATES[-1]:
        return 44100 if rate % 44100 == 0 else 48000
    return next(valid for valid in MP3_SAMPLE_RATES if valid >= rate)


def is_high_resolution(stream: "AudioStream") -> bool:
    """More than 16 bits per sample (24-bit FLAC/WAV). Lossy sources have no bit depth."""
    return (stream.bit_depth or 0) > 16


def audio_args(stream: "AudioStream", target: Format) -> list[str]:
    """FFmpeg output arguments converting `stream` to `target` (wav, flac or mp3).

    Only the first audio stream is converted (cover art and other streams are dropped);
    tags are copied.
    """
    args = ["-map", "0:a:0", "-map_metadata", "0"]
    high_res = is_high_resolution(stream)

    if target is Format.WAV:
        return [*args, "-c:a", "pcm_s24le" if high_res else "pcm_s16le"]

    if target is Format.FLAC:
        args += ["-c:a", "flac", "-compression_level", FLAC_COMPRESSION_LEVEL]
        if high_res:  # 24-bit samples travel in 32-bit containers
            return [*args, "-sample_fmt", "s32", "-bits_per_raw_sample", "24"]
        return [*args, "-sample_fmt", "s16"]

    if target is Format.MP3:
        args += ["-c:a", "libmp3lame", "-q:a", MP3_VBR_QUALITY, "-id3v2_version", "3"]
        if stream.sample_rate and mp3_sample_rate(stream.sample_rate) != stream.sample_rate:
            args += ["-ar", str(mp3_sample_rate(stream.sample_rate))]
        if stream.channels > MP3_MAX_CHANNELS:
            args += ["-ac", str(MP3_MAX_CHANNELS)]
        return args

    raise ValueError(f"{target} is not an audio format")
