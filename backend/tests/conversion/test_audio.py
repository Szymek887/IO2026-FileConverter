"""Audio converter (flac / mp3 / wav): presets and real conversions."""

import subprocess

import pytest
from PIL import Image

from app.conversion.converters import CONVERTERS, convert, presets
from app.conversion.converters.ffmpeg import run_ffprobe
from app.conversion.formats import Category, Format
from app.conversion.probe import AudioStream, probe
from app.core.config import settings
from tests.conversion.conftest import SINE, _ffmpeg, requires_ffmpeg

# --- presets (no FFmpeg needed) --------------------------------------------------------


def stream(bit_depth=16, sample_rate=44100, channels=2, codec="pcm_s16le") -> AudioStream:
    return AudioStream(codec=codec, sample_rate=sample_rate, channels=channels, bit_depth=bit_depth)


def test_audio_converter_is_registered():
    assert CONVERTERS[Category.AUDIO].__name__ == "convert_audio"


@pytest.mark.parametrize(
    ("rate", "expected"),
    [
        (44100, 44100),
        (48000, 48000),
        (22050, 22050),
        (88200, 44100),
        (176400, 44100),
        (96000, 48000),
        (192000, 48000),
        (37800, 44100),
        (7000, 8000),
    ],
)
def test_mp3_sample_rate(rate, expected):
    assert presets.mp3_sample_rate(rate) == expected


@pytest.mark.parametrize(
    ("source", "codec"),
    [(stream(16), "pcm_s16le"), (stream(24), "pcm_s24le"), (stream(None), "pcm_s16le")],
)
def test_wav_codec_follows_bit_depth(source, codec):
    args = presets.audio_args(source, Format.WAV)
    assert args[args.index("-c:a") + 1] == codec


def test_flac_keeps_24_bit():
    args = presets.audio_args(stream(24), Format.FLAC)
    assert args[args.index("-sample_fmt") + 1] == "s32"
    assert args[args.index("-bits_per_raw_sample") + 1] == "24"
    assert "s16" in presets.audio_args(stream(16), Format.FLAC)


def test_mp3_preset():
    args = presets.audio_args(stream(24, sample_rate=96000, channels=6), Format.MP3)
    assert args[args.index("-c:a") + 1] == "libmp3lame"
    assert args[args.index("-q:a") + 1] == "0"
    assert args[args.index("-ar") + 1] == "48000"
    assert args[args.index("-ac") + 1] == "2"
    plain = presets.audio_args(stream(), Format.MP3)
    assert "-ar" not in plain and "-ac" not in plain


def test_only_first_audio_stream_and_tags_are_mapped():
    for target in (Format.WAV, Format.FLAC, Format.MP3):
        args = presets.audio_args(stream(), target)
        assert args[:4] == ["-map", "0:a:0", "-map_metadata", "0"]


def test_non_audio_target_is_rejected():
    with pytest.raises(ValueError):
        presets.audio_args(stream(), Format.PNG)


# --- real conversions ------------------------------------------------------------------


def pcm_md5(path, fmt: Format, codec: str) -> str:
    """MD5 of the decoded samples, independent of the container."""
    out = subprocess.run(
        [settings.ffmpeg_path, "-v", "error", "-f", fmt.value if fmt is not Format.MP3 else "mp3",
         "-i", str(path), "-map", "0:a:0", "-c:a", codec, "-f", "md5", "-"],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return out.strip()


def run(src, source, target, tmp_path):
    dst = tmp_path / f"out.{target}"
    convert(src, dst, source, target, settings.conversion_timeout_seconds)
    return probe(dst, target)


@requires_ffmpeg
@pytest.mark.parametrize(
    ("name", "source", "target", "codec", "bits", "rate", "channels"),
    [
        ("stereo16.wav", Format.WAV, Format.FLAC, "flac", 16, 44100, 2),
        ("stereo16.wav", Format.WAV, Format.MP3, "mp3", None, 44100, 2),
        ("mono24.wav", Format.WAV, Format.FLAC, "flac", 24, 48000, 1),
        ("mono24.flac", Format.FLAC, Format.WAV, "pcm_s24le", 24, 48000, 1),
        ("mono24.flac", Format.FLAC, Format.MP3, "mp3", None, 48000, 1),
        ("song.mp3", Format.MP3, Format.WAV, "pcm_s16le", 16, 44100, 2),
        ("song.mp3", Format.MP3, Format.FLAC, "flac", 16, 44100, 2),
    ],
)
def test_conversion_pairs(media, tmp_path, name, source, target, codec, bits, rate, channels):
    info = run(media / name, source, target, tmp_path)
    assert info.format is target
    assert info.audio.codec == codec
    assert info.audio.bit_depth == bits
    assert (info.audio.sample_rate, info.audio.channels) == (rate, channels)
    assert info.duration == pytest.approx(1.0, abs=0.06)


@requires_ffmpeg
@pytest.mark.parametrize(
    ("name", "source", "target", "codec"),
    [
        ("stereo16.wav", Format.WAV, Format.FLAC, "pcm_s16le"),
        ("mono24.wav", Format.WAV, Format.FLAC, "pcm_s24le"),
        ("mono24.flac", Format.FLAC, Format.WAV, "pcm_s24le"),
    ],
)
def test_lossless_pairs_are_bit_exact(media, tmp_path, name, source, target, codec):
    dst = tmp_path / f"out.{target}"
    convert(media / name, dst, source, target, 60)
    assert pcm_md5(dst, target, codec) == pcm_md5(media / name, source, codec)


@requires_ffmpeg
def test_hi_res_surround_to_mp3(tmp_path):
    src = tmp_path / "surround.wav"
    _ffmpeg(*SINE, "-ar", "96000", "-ac", "6", "-c:a", "pcm_s24le", str(src))
    info = run(src, Format.WAV, Format.MP3, tmp_path)
    assert (info.audio.sample_rate, info.audio.channels) == (48000, 2)


@requires_ffmpeg
def test_88_2_khz_halves_to_44_1_for_mp3(tmp_path):
    src = tmp_path / "hires.flac"
    _ffmpeg(*SINE, "-ar", "88200", "-c:a", "flac", str(src))
    assert run(src, Format.FLAC, Format.MP3, tmp_path).audio.sample_rate == 44100


@requires_ffmpeg
def test_tags_are_kept(tmp_path):
    src = tmp_path / "tagged.flac"
    _ffmpeg(*SINE, "-c:a", "flac", "-metadata", "title=Zażółć gęślą jaźń", "-metadata",
            "artist=Zespół", str(src))  # fmt: skip
    dst = tmp_path / "out.mp3"
    convert(src, dst, Format.FLAC, Format.MP3, 60)
    tags = {k.lower(): v for k, v in run_ffprobe(dst, Format.MP3, 30)["format"]["tags"].items()}
    assert tags["title"] == "Zażółć gęślą jaźń"
    assert tags["artist"] == "Zespół"


@requires_ffmpeg
def test_cover_art_is_dropped(media, tmp_path):
    cover = tmp_path / "cover.png"
    Image.new("RGB", (16, 16), "red").save(cover)
    src = tmp_path / "with_cover.mp3"
    _ffmpeg("-i", str(media / "song.mp3"), "-i", str(cover), "-map", "0", "-map", "1",
            "-c", "copy", "-id3v2_version", "3", "-disposition:v", "attached_pic",
            str(src))  # fmt: skip
    assert len(run_ffprobe(src, Format.MP3, 30)["streams"]) == 2

    dst = tmp_path / "out.flac"
    convert(src, dst, Format.MP3, Format.FLAC, 60)
    streams = run_ffprobe(dst, Format.FLAC, 30)["streams"]
    assert [s["codec_type"] for s in streams] == ["audio"]


# --- through the worker ----------------------------------------------------------------


@requires_ffmpeg
def test_audio_job_end_to_end(auth_client, db, media):
    from app.conversion import storage
    from app.conversion.models import Job, JobStatus
    from app.conversion.worker import process_job

    response = auth_client.post(
        "/api/jobs",
        files=[
            ("files", ("nagranie.wav", (media / "stereo16.wav").read_bytes())),
            ("files", ("muzyka.flac", (media / "mono24.flac").read_bytes())),
        ],
        data={"target_format": "mp3"},
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]

    process_job(job_id)

    job = db.get(Job, job_id)
    assert job.status is JobStatus.DONE, job.result.message
    assert [o.name for o in job.result.outputs] == ["nagranie.mp3", "muzyka.mp3"]
    for out in job.result.outputs:
        assert probe(storage.to_absolute(out.path), Format.MP3).audio.codec == "mp3"
