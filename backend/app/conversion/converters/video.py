"""Video converter: mp4 / mov / gif via FFmpeg, parameters from `presets.video_plans`."""

import logging
import math
import time
from pathlib import Path

from app.conversion import probe as media_probe  # module import: probe imports this package
from app.conversion.converters import presets
from app.conversion.converters.ffmpeg import FFmpegError, run_ffmpeg
from app.conversion.formats import Format

logger = logging.getLogger(__name__)


def convert_video(src: Path, dst: Path, source: Format, target: Format, timeout: int) -> None:
    info = media_probe.probe(src, source)
    if info.video is None:  # probe() already guarantees this for video formats
        raise ValueError("no video stream")

    # All attempts share `timeout`, so a failed remux doesn't double the time limit.
    deadline = time.monotonic() + timeout
    *attempts, last = presets.video_plans(info, target)
    for args in attempts:
        try:
            run_ffmpeg(src, source, args, dst, target, _remaining(deadline))
            return
        except FFmpegError as exc:
            if exc.timeout:
                raise
            logger.info("Remux %s -> %s failed, transcoding: %s", source, target, exc)
    run_ffmpeg(src, source, last, dst, target, _remaining(deadline))


def _remaining(deadline: float) -> int:
    return max(1, math.ceil(deadline - time.monotonic()))
