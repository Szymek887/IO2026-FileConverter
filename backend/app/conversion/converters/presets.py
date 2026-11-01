"""Every quality parameter of the conversion engine, in one place.

The user doesn't choose parameters – these functions pick them from what `probe()` found,
following the requirements: lossless where both formats allow it (FLAC, WAV), otherwise the
highest sensible quality (MP3). Tune quality here without touching the converter logic.
"""

from typing import TYPE_CHECKING

from app.conversion.formats import Format

if TYPE_CHECKING:  # probe.py imports this package, so no runtime import from it
    from app.conversion.probe import AudioStream, MediaInfo

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


# --- video -----------------------------------------------------------------------------

X264_CRF = "18"  # visually lossless
X264_PRESET = "medium"  # "slow": 2x the time, same size (B12 benchmark); don't touch the CRF
AAC_BITRATE = "256k"
# Codecs an .mp4 can hold; anything else in a .mov has to be converted.
MP4_VIDEO_CODECS = frozenset({"h264", "hevc", "av1", "mpeg4"})
MP4_AUDIO_CODECS = frozenset({"aac", "mp3", "alac", "ac3", "eac3"})
GIF_MAX_FPS = 15.0
GIF_MAX_WIDTH = 640
# Long clips get smaller GIFs, otherwise the output would be enormous.
GIF_LONG_CLIP_SECONDS = 60
GIF_LONG_CLIP_FPS = 10.0
GIF_LONG_CLIP_WIDTH = 480


def _aac_args() -> list[str]:
    return ["-c:a", "aac", "-b:a", AAC_BITRATE]


def _container_args(target: Format) -> list[str]:
    return ["-movflags", "+faststart"] if target is Format.MP4 else []


def _remux_args(info: "MediaInfo", target: Format) -> list[str]:
    """Keep the video stream as it is (no quality loss, takes seconds). Audio is converted
    only if a track doesn't belong in `target`. Mapping streams explicitly drops data
    tracks (iPhone), which the mp4 muxer can't write."""
    args = ["-map", "0:V:0", "-map", "0:a?", "-map_metadata", "0", "-c:v", "copy"]
    if info.video.codec == "hevc":
        args += ["-tag:v", "hvc1"]  # Apple players refuse the default hev1 tag
    if target is Format.MP4 and not MP4_AUDIO_CODECS.issuperset(info.audio_codecs):
        args += _aac_args()
    else:
        args += ["-c:a", "copy"]
    return [*args, *_container_args(target)]


def _transcode_args(info: "MediaInfo", target: Format) -> list[str]:
    """Re-encode to H.264/AAC. The scale filter rounds odd sizes down: yuv420p needs even
    ones. FFmpeg applies rotation metadata on its own before the filter."""
    args = ["-map", "0:V:0", "-map", "0:a?", "-map_metadata", "0"]
    args += ["-c:v", "libx264", "-crf", X264_CRF, "-preset", X264_PRESET]
    args += ["-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2"]
    args += ["-an"] if info.format is Format.GIF else _aac_args()
    return [*args, *_container_args(target)]


def _gif_args(info: "MediaInfo") -> list[str]:
    """One pass with a palette computed for this clip. Width is limited in the filter, not
    from `info`: only there it is the width after rotation, and small clips aren't upscaled."""
    long_clip = (info.duration or 0) > GIF_LONG_CLIP_SECONDS
    max_fps = GIF_LONG_CLIP_FPS if long_clip else GIF_MAX_FPS
    max_width = GIF_LONG_CLIP_WIDTH if long_clip else GIF_MAX_WIDTH
    fps = min(info.video.fps or max_fps, max_fps)
    graph = (
        f"[0:V:0]fps={fps:.3f},scale='min(iw,{max_width})':-1:flags=lanczos,split[a][b];"
        "[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a[out]"
    )
    return ["-filter_complex", graph, "-map", "[out]", "-loop", "0"]


def video_plans(info: "MediaInfo", target: Format) -> list[list[str]]:
    """FFmpeg output arguments to try in order (a later one only if the previous failed).

    A remux is always followed by a transcode: probing can't foresee everything a muxer
    refuses (e.g. Opus audio in a .mov).
    """
    if target is Format.GIF:
        return [_gif_args(info)]
    if target not in (Format.MP4, Format.MOV):
        raise ValueError(f"{target} is not a video format")
    transcode = _transcode_args(info, target)
    if info.format is Format.GIF:
        return [transcode]
    if target is Format.MP4 and info.video.codec not in MP4_VIDEO_CODECS:
        return [transcode]
    return [_remux_args(info, target), transcode]


# --- images ----------------------------------------------------------------------------

PNG_COMPRESS_LEVEL = 6  # PNG is lossless at every level; 6 is the speed/size sweet spot
JPEG_QUALITY = 95
JPEG_SUBSAMPLING = 0  # 4:4:4 – no chroma subsampling, keeps sharp colour edges
HEIC_QUALITY = 90
# Large HEICs are stored as a grid of tiles (like iPhones do). A single HEVC frame of a
# detailed 24–48 MP photo can exceed what decoders (libde265) accept – the file would not
# open. 2048 px tiles fix that at the same encoding speed (512 px tiles: ~3x slower).
HEIC_GRID_TILE_SIZE = 2048
FLATTEN_BACKGROUND = (255, 255, 255)  # transparent areas become white in JPG


def image_save_options(target: Format) -> dict[str, object]:
    """Pillow `save()` keyword arguments for `target` (jpg, png or heic)."""
    if target is Format.PNG:
        return {"compress_level": PNG_COMPRESS_LEVEL}
    if target is Format.JPG:
        return {"quality": JPEG_QUALITY, "subsampling": JPEG_SUBSAMPLING, "optimize": True}
    if target is Format.HEIC:
        return {"quality": HEIC_QUALITY}
    raise ValueError(f"{target} is not an image format")
