import functools
import logging
import shutil
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    ffmpeg: bool


@functools.cache
def ffmpeg_available() -> bool:
    """Whether both `FFMPEG_PATH` and `FFPROBE_PATH` resolve to executables (names are looked
    up on PATH). Checked once per process."""
    return all(shutil.which(tool) for tool in (settings.ffmpeg_path, settings.ffprobe_path))


def enough_disk_space() -> bool:
    return shutil.disk_usage(settings.data_dir).free >= settings.min_free_disk_bytes


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "Degraded"}},
)
def health(response: Response) -> HealthResponse:
    """Liveness check. No authentication required."""
    ffmpeg = ffmpeg_available()
    disk = enough_disk_space()
    if ffmpeg and disk:
        return HealthResponse(status="ok", ffmpeg=True)

    logger.warning("Health degraded: ffmpeg=%s, enough_disk_space=%s", ffmpeg, disk)
    response.status_code = 503
    return HealthResponse(status="degraded", ffmpeg=ffmpeg)
