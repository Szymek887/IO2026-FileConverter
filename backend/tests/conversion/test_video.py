"""Video converter (mp4 / mov / gif): decision table and real conversions."""

import subprocess

import pytest

from app.conversion.converters import CONVERTERS, ConversionError, convert, presets, video
from app.conversion.converters.ffmpeg import FFmpegError, run_ffmpeg, run_ffprobe
from app.conversion.formats import Category, Format
from app.conversion.probe import AudioStream, MediaInfo, VideoStream, probe
from app.core.config import settings
from tests.conversion.conftest import SINE, TESTSRC, _ffmpeg, requires_ffmpeg

# --- decision table (no FFmpeg needed) -------------------------------------------------


def clip(fmt=Format.MOV, codec="h264", audio="aac", fps=25.0, width=1920, duration=10.0):
    return MediaInfo(
        format=fmt,
        duration=duration,
        video=VideoStream(codec=codec, width=width, height=1080, fps=fps),
        audio=AudioStream(codec=audio, sample_rate=48000, channels=2, bit_depth=None)
        if audio
        else None,
        audio_codecs=(audio,) if audio else (),
    )


def value(args, flag):
    return args[args.index(flag) + 1]


def test_video_converter_is_registered():
    assert CONVERTERS[Category.VIDEO].__name__ == "convert_video"


@pytest.mark.parametrize("codec", ["h264", "hevc", "av1", "mpeg4"])
@pytest.mark.parametrize("audio", ["aac", "mp3", "alac", "ac3", "eac3", None])
def test_mov_to_mp4_remuxes_compatible_streams(codec, audio):
    remux, transcode = presets.video_plans(clip(codec=codec, audio=audio), Format.MP4)
    assert value(remux, "-c:v") == "copy"
    assert value(remux, "-c:a") == "copy"
    assert value(remux, "-movflags") == "+faststart"
    assert value(transcode, "-c:v") == "libx264"


def test_incompatible_audio_only_converts_the_audio():
    remux, _ = presets.video_plans(clip(audio="pcm_s16le"), Format.MP4)
    assert value(remux, "-c:v") == "copy"
    assert value(remux, "-c:a") == "aac"
    assert value(remux, "-b:a") == "256k"


def test_incompatible_video_goes_straight_to_transcode():
    plans = presets.video_plans(clip(codec="prores"), Format.MP4)
    assert len(plans) == 1
    assert value(plans[0], "-c:v") == "libx264"


def test_mp4_to_mov_remuxes_with_transcode_fallback():
    remux, transcode = presets.video_plans(clip(Format.MP4), Format.MOV)
    assert value(remux, "-c:v") == value(remux, "-c:a") == "copy"
    assert value(transcode, "-c:v") == "libx264"
    assert "-movflags" not in remux and "-movflags" not in transcode


def test_hevc_is_tagged_for_apple_players():
    for fmt, target in ((Format.MOV, Format.MP4), (Format.MP4, Format.MOV)):
        remux, _ = presets.video_plans(clip(fmt, codec="hevc"), target)
        assert value(remux, "-tag:v") == "hvc1"
    remux, _ = presets.video_plans(clip(), Format.MP4)
    assert "-tag:v" not in remux


def test_transcode_preset():
    _, args = presets.video_plans(clip(), Format.MP4)
    assert value(args, "-crf") == "18"
    assert value(args, "-preset") == "medium"
    assert value(args, "-pix_fmt") == "yuv420p"
    assert value(args, "-vf") == "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    assert value(args, "-c:a") == "aac"
    assert value(args, "-movflags") == "+faststart"


@pytest.mark.parametrize("target", [Format.MP4, Format.MOV])
def test_gif_source_is_transcoded_without_audio(target):
    plans = presets.video_plans(clip(Format.GIF, audio=None), target)
    assert len(plans) == 1
    assert value(plans[0], "-c:v") == "libx264"
    assert "-an" in plans[0]


@pytest.mark.parametrize(
    ("fps", "duration", "expected"),
    [
        (25.0, 10.0, "fps=15.000,scale='min(iw,640)'"),
        (10.0, 10.0, "fps=10.000,scale='min(iw,640)'"),
        (None, 10.0, "fps=15.000,scale='min(iw,640)'"),
        (25.0, 60.0, "fps=15.000,scale='min(iw,640)'"),
        (25.0, 60.5, "fps=10.000,scale='min(iw,480)'"),
        (5.0, 120.0, "fps=5.000,scale='min(iw,480)'"),
        (25.0, None, "fps=15.000,scale='min(iw,640)'"),
    ],
)
def test_gif_fps_and_width_rules(fps, duration, expected):
    [args] = presets.video_plans(clip(fps=fps, duration=duration), Format.GIF)
    assert expected in value(args, "-filter_complex")
    assert value(args, "-loop") == "0"


def test_non_video_target_is_rejected():
    with pytest.raises(ValueError):
        presets.video_plans(clip(), Format.MP3)


# --- fallback (FFmpeg faked) -----------------------------------------------------------


def fake_ffmpeg(monkeypatch, tmp_path, *outcomes):
    """Replaces probe and run_ffmpeg; returns the list of (args, timeout) of the calls."""
    calls = []
    results = iter(outcomes)

    def run(src, source, args, dst, target, timeout):
        calls.append((args, timeout))
        result = next(results)
        if isinstance(result, Exception):
            raise result
        dst.write_bytes(b"out")

    monkeypatch.setattr(video.media_probe, "probe", lambda *_: clip(Format.MP4))
    monkeypatch.setattr(video, "run_ffmpeg", run)
    return calls


def test_failed_remux_falls_back_to_transcode(monkeypatch, tmp_path):
    calls = fake_ffmpeg(monkeypatch, tmp_path, FFmpegError("muxer refused"), None)
    dst = tmp_path / "out.mov"
    convert(tmp_path / "in.mp4", dst, Format.MP4, Format.MOV, 600)
    assert [value(args, "-c:v") for args, _ in calls] == ["copy", "libx264"]
    assert dst.read_bytes() == b"out"


def test_timed_out_remux_is_not_retried(monkeypatch, tmp_path):
    calls = fake_ffmpeg(monkeypatch, tmp_path, FFmpegError("slow", timeout=True))
    with pytest.raises(ConversionError) as exc:
        convert(tmp_path / "in.mp4", tmp_path / "out.mov", Format.MP4, Format.MOV, 600)
    assert exc.value.timeout is True
    assert len(calls) == 1


def test_fallback_only_gets_the_remaining_time(monkeypatch, tmp_path):
    calls = fake_ffmpeg(monkeypatch, tmp_path, FFmpegError("muxer refused"), None)
    ticks = iter([1000.0, 1000.0, 1400.0])
    monkeypatch.setattr(video.time, "monotonic", lambda: next(ticks))
    convert(tmp_path / "in.mp4", tmp_path / "out.mov", Format.MP4, Format.MOV, 600)
    assert [timeout for _, timeout in calls] == [600, 200]


def test_failing_transcode_is_a_conversion_error(monkeypatch, tmp_path):
    fake_ffmpeg(monkeypatch, tmp_path, FFmpegError("no"), FFmpegError("still no"))
    with pytest.raises(ConversionError):
        convert(tmp_path / "in.mp4", tmp_path / "out.mov", Format.MP4, Format.MOV, 600)
    assert list(tmp_path.glob("out.*")) == []


# --- real conversions ------------------------------------------------------------------


def run(src, source, target, tmp_path):
    dst = tmp_path / f"out.{target}"
    convert(src, dst, source, target, settings.conversion_timeout_seconds)
    return dst, probe(dst, target)


def video_md5(path) -> str:
    """MD5 of the encoded video packets, independent of the container."""
    return subprocess.run(
        [settings.ffmpeg_path, "-v", "error", "-i", str(path), "-map", "0:v:0", "-c", "copy",
         "-f", "md5", "-"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip


def gif_frames(path) -> int:
    return int(
        subprocess.run(
            [settings.ffprobe_path, "-v", "error", "-f", "gif", "-count_frames", "-select_streams",
             "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, check=True,
        ).stdout.strip().rstrip(",")
    )  # fmt: skip


def rotation(path, fmt: Format) -> int | None:
    stream = next(s for s in run_ffprobe(path, fmt, 30)["streams"] if s["codec_type"] == "video")
    side_data = [d for d in stream.get("side_data_list", []) if "rotation" in d]
    return abs(int(side_data[0]["rotation"])) if side_data else None


def h264_clip(path, size="320x240"):
    _ffmpeg("-f", "lavfi", "-i", f"testsrc2=size={size}:rate=25:duration=1", *SINE,
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", str(path))  # fmt: skip
    return path


def prores_clip(path):
    _ffmpeg(*TESTSRC, *SINE, "-c:v", "prores_ks", "-profile:v", "1", "-c:a", "pcm_s16le",
            "-shortest", str(path))  # fmt: skip
    return path


def hevc_clip(path, pix_fmt="yuv420p"):
    _ffmpeg(*TESTSRC, *SINE, "-c:v", "libx265", "-preset", "ultrafast", "-x265-params",
            "log-level=error", "-pix_fmt", pix_fmt, "-c:a", "aac", "-shortest",
            str(path))  # fmt: skip
    return path


def rotated(src, path):
    _ffmpeg("-display_rotation", "90", "-i", str(src), "-c", "copy", str(path))
    return path


@requires_ffmpeg
@pytest.mark.parametrize(
    ("name", "source", "target", "codec"),
    [
        ("clip.mp4", Format.MP4, Format.MOV, "h264"),
        ("clip_pcm.mov", Format.MOV, Format.MP4, "h264"),
        ("clip.mp4", Format.MP4, Format.GIF, "gif"),
        ("clip_pcm.mov", Format.MOV, Format.GIF, "gif"),
        ("anim.gif", Format.GIF, Format.MP4, "h264"),
        ("anim.gif", Format.GIF, Format.MOV, "h264"),
    ],
)
def test_conversion_pairs(media, tmp_path, name, source, target, codec):
    _, info = run(media / name, source, target, tmp_path)
    assert info.format is target
    assert info.video.codec == codec
    assert (info.video.width, info.video.height) == (320, 240)
    assert info.duration == pytest.approx(1.0, abs=0.1)
    if source is Format.GIF or target is Format.GIF:
        assert info.audio is None
    else:
        assert info.audio is not None


@requires_ffmpeg
def test_remux_keeps_the_video_bit_identical(media, tmp_path):
    dst, info = run(media / "clip.mp4", Format.MP4, Format.MOV, tmp_path)
    assert info.audio.codec == "aac"
    assert video_md5(dst) == video_md5(media / "clip.mp4")


@requires_ffmpeg
def test_pcm_audio_is_converted_and_video_kept(media, tmp_path):
    dst, info = run(media / "clip_pcm.mov", Format.MOV, Format.MP4, tmp_path)
    assert info.audio.codec == "aac"
    assert video_md5(dst) == video_md5(media / "clip_pcm.mov")


@requires_ffmpeg
def test_faststart_moves_the_index_to_the_front(media, tmp_path):
    dst, _ = run(media / "clip_pcm.mov", Format.MOV, Format.MP4, tmp_path)
    data = dst.read_bytes()
    assert data.index(b"moov") < data.index(b"mdat")


@requires_ffmpeg
def test_prores_is_transcoded(tmp_path):
    src = prores_clip(tmp_path / "prores.mov")
    assert probe(src, Format.MOV).video.codec == "prores"
    _, info = run(src, Format.MOV, Format.MP4, tmp_path)
    assert info.video.codec == "h264"
    assert info.audio.codec == "aac"
    assert (info.video.width, info.video.height) == (320, 240)


@requires_ffmpeg
def test_hevc_is_remuxed_with_hvc1_tag(tmp_path):
    src = hevc_clip(tmp_path / "hevc.mov")
    dst, info = run(src, Format.MOV, Format.MP4, tmp_path)
    assert info.video.codec == "hevc"
    streams = run_ffprobe(dst, Format.MP4, 30)["streams"]
    tags = [s["codec_tag_string"] for s in streams if s["codec_type"] == "video"]
    assert tags == ["hvc1"]
    assert video_md5(dst) == video_md5(src)


@requires_ffmpeg
def test_10_bit_hevc_remuxes_and_converts_to_gif(tmp_path):
    src = hevc_clip(tmp_path / "hdr.mov", "yuv420p10le")
    _, info = run(src, Format.MOV, Format.MP4, tmp_path)
    assert info.video.codec == "hevc"
    _, info = run(src, Format.MOV, Format.GIF, tmp_path)
    assert info.video.codec == "gif"


@requires_ffmpeg
def test_10_bit_hevc_transcode_doesnt_fail(tmp_path):
    src = hevc_clip(tmp_path / "hdr.mov", "yuv420p10le")
    info = probe(src, Format.MOV)
    _, args = presets.video_plans(info, Format.MP4)
    dst = tmp_path / "out.mp4"
    run_ffmpeg(src, Format.MOV, args, dst, Format.MP4, 60)
    assert probe(dst, Format.MP4).video.codec == "h264"


@requires_ffmpeg
def test_mp4_codec_mov_refuses_falls_back_to_transcode(tmp_path):
    src = tmp_path / "opus.mp4"
    _ffmpeg(*TESTSRC, *SINE, "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "libopus", "-shortest", str(src))  # fmt: skip
    _, info = run(src, Format.MP4, Format.MOV, tmp_path)
    assert info.video.codec == "h264"
    assert info.audio.codec == "aac"


@requires_ffmpeg
def test_second_incompatible_audio_track_is_converted_too(media, tmp_path):
    src = tmp_path / "two_tracks.mov"
    _ffmpeg("-i", str(media / "clip.mp4"), *SINE, "-map", "0", "-map", "1:a", "-c:v", "copy",
            "-c:a:0", "copy", "-c:a:1", "pcm_s16le", str(src))  # fmt: skip
    dst, info = run(src, Format.MOV, Format.MP4, tmp_path)
    audio = [s for s in run_ffprobe(dst, Format.MP4, 30)["streams"] if s["codec_type"] == "audio"]
    assert [s["codec_name"] for s in audio] == ["aac", "aac"]
    assert video_md5(dst) == video_md5(src)
    assert info.video.codec == "h264"


@requires_ffmpeg
def test_timecode_track_doesnt_break_the_remux(media, tmp_path):
    src = tmp_path / "timecode.mov"
    _ffmpeg("-i", str(media / "clip.mp4"), "-c", "copy", "-timecode", "01:00:00:00", str(src))
    kinds = [s["codec_type"] for s in run_ffprobe(src, Format.MOV, 30)["streams"]]
    assert "data" in kinds

    dst, info = run(src, Format.MOV, Format.MP4, tmp_path)
    assert (info.video.codec, info.audio.codec) == ("h264", "aac")
    assert video_md5(dst) == video_md5(src)


@requires_ffmpeg
def test_cover_art_before_the_video_is_not_mapped(media, tmp_path):
    from PIL import Image

    cover = tmp_path / "cover.png"
    Image.new("RGB", (16, 16), "red").save(cover)
    src = tmp_path / "cover.mov"
    _ffmpeg("-i", str(cover), "-i", str(media / "clip.mp4"), "-map", "0", "-map", "1",
            "-c", "copy", "-disposition:v:0", "attached_pic", str(src))  # fmt: skip

    _, info = run(src, Format.MOV, Format.MP4, tmp_path)
    assert (info.video.codec, info.video.width) == ("h264", 320)


@requires_ffmpeg
def test_odd_dimensions_become_even(tmp_path):
    src = prores_clip_odd(tmp_path / "odd.mov")
    _, info = run(src, Format.MOV, Format.MP4, tmp_path)
    assert (info.video.width, info.video.height) == (320, 240)


def prores_clip_odd(path):
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=321x241:rate=25:duration=1",
            "-c:v", "prores_ks", "-profile:v", "1", str(path))  # fmt: skip
    return path


@requires_ffmpeg
def test_gif_with_odd_dimensions_and_transparency(tmp_path):
    src = tmp_path / "odd.gif"
    _ffmpeg("-f", "lavfi", "-i", "color=c=red@0.0:size=33x21:rate=10:duration=1,format=rgba",
            str(src))  # fmt: skip
    _, info = run(src, Format.GIF, Format.MP4, tmp_path)
    assert (info.video.width, info.video.height) == (32, 20)


@requires_ffmpeg
def test_remux_keeps_rotation(media, tmp_path):
    src = rotated(media / "clip.mp4", tmp_path / "rotated.mov")
    assert rotation(src, Format.MOV) == 90
    dst, info = run(src, Format.MOV, Format.MP4, tmp_path)
    assert rotation(dst, Format.MP4) == 90
    assert (info.video.width, info.video.height) == (320, 240)


@requires_ffmpeg
def test_transcode_applies_rotation_once(tmp_path):
    src = rotated(prores_clip(tmp_path / "prores.mov"), tmp_path / "rotated.mov")
    dst, info = run(src, Format.MOV, Format.MP4, tmp_path)
    assert (info.video.width, info.video.height) == (240, 320)
    assert not rotation(dst, Format.MP4)


@requires_ffmpeg
def test_gif_of_a_rotated_clip_is_portrait_and_not_upscaled(media, tmp_path):
    src = rotated(media / "clip.mp4", tmp_path / "rotated.mov")
    _, info = run(src, Format.MOV, Format.GIF, tmp_path)
    assert (info.video.width, info.video.height) == (240, 320)


@requires_ffmpeg
def test_gif_limits_fps_and_width(tmp_path):
    src = h264_clip(tmp_path / "wide.mp4", "800x600")
    dst, info = run(src, Format.MP4, Format.GIF, tmp_path)
    assert (info.video.width, info.video.height) == (640, 480)
    assert gif_frames(dst) == pytest.approx(15, abs=1)  # 1 s; GIF delays are in 1/100 s


@requires_ffmpeg
def test_gif_of_a_long_clip_is_smaller(tmp_path):
    src = tmp_path / "long.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=800x100:rate=12:duration=61", "-c:v", "libx264",
            "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(src))  # fmt: skip
    dst, info = run(src, Format.MP4, Format.GIF, tmp_path)
    assert (info.video.width, info.video.height) == (480, 60)
    assert gif_frames(dst) == pytest.approx(610, abs=2)


# --- through the worker ----------------------------------------------------------------


@requires_ffmpeg
def test_video_job_end_to_end(auth_client, db, media):
    from app.conversion import storage
    from app.conversion.models import Job, JobStatus
    from app.conversion.worker import process_job

    response = auth_client.post(
        "/api/jobs",
        files=[
            ("files", ("film.mov", (media / "clip_pcm.mov").read_bytes())),
            ("files", ("animacja.gif", (media / "anim.gif").read_bytes())),
        ],
        data={"target_format": "mp4"},
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]

    process_job(job_id)

    job = db.get(Job, job_id)
    assert job.status is JobStatus.DONE, job.result.message
    assert [o.name for o in job.result.outputs] == ["film.mp4", "animacja.mp4"]
    for out in job.result.outputs:
        assert probe(storage.to_absolute(out.path), Format.MP4).video.codec == "h264"
